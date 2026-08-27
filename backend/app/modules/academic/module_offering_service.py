from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import AcademicModule, Batch, Intake, ModuleOffering, RoutineEntry, RoutineEntrySection, Section


def offering_section_ids(db: Session, offering: ModuleOffering) -> set[int]:
    return set(db.scalars(select(Section.id).join(Section.module_offerings).where(ModuleOffering.id == offering.id)))


def cohort_sections(
    db: Session,
    *,
    intake_id: int,
    batch_id: int,
    semester_number: int,
) -> list[Section]:
    """Return every section that belongs to an offering's cohort.

    Null intake/semester values are retained for older section records. They
    become part of the selected cohort only when the batch matches, which is
    the same compatibility rule used by routine validation.
    """

    return list(
        db.scalars(
            select(Section)
            .where(
                Section.batch_id == batch_id,
                or_(Section.intake_id == intake_id, Section.intake_id.is_(None)),
                or_(Section.semester_number == semester_number, Section.semester_number.is_(None)),
            )
            .order_by(Section.name, Section.id)
        )
    )


def routine_uses_offering_section(db: Session, offering_id: int, section_id: int) -> bool:
    """Whether removing a section from an offering would invalidate a routine."""

    return bool(
        db.scalar(
            select(RoutineEntry.id)
            .outerjoin(RoutineEntrySection)
            .where(
                RoutineEntry.module_offering_id == offering_id,
                or_(RoutineEntry.section_id == section_id, RoutineEntrySection.section_id == section_id),
            )
        )
    )


def synchronize_offering_sections(db: Session, offering: ModuleOffering) -> list[Section]:
    """Make an offering cover all and only its intake/batch/semester sections."""

    sections = cohort_sections(
        db,
        intake_id=offering.intake_id,
        batch_id=offering.batch_id,
        semester_number=offering.semester_number,
    )
    requested_ids = {section.id for section in sections}
    for section_id in offering_section_ids(db, offering) - requested_ids:
        if routine_uses_offering_section(db, offering.id, section_id):
            section = db.get(Section, section_id)
            raise HTTPException(
                409,
                f"Section {section.name if section else section_id} cannot leave this cohort because an existing routine uses it",
            )
    offering.sections[:] = sections
    db.flush()
    return sections


def synchronize_section_module_offerings(db: Session, section: Section) -> list[ModuleOffering]:
    """Attach a section to every offering in its cohort and detach stale links."""

    current = list(section.module_offerings)
    if section.intake_id is None or section.semester_number is None:
        desired: list[ModuleOffering] = []
    else:
        desired = list(
            db.scalars(
                select(ModuleOffering).where(
                    ModuleOffering.intake_id == section.intake_id,
                    ModuleOffering.batch_id == section.batch_id,
                    ModuleOffering.semester_number == section.semester_number,
                )
            )
        )
    desired_ids = {offering.id for offering in desired}
    for offering in current:
        if offering.id not in desired_ids and routine_uses_offering_section(db, offering.id, section.id):
            raise HTTPException(
                409,
                f"Section {section.name} cannot move to a different cohort because an existing routine uses it",
            )
    section.module_offerings[:] = desired
    db.flush()
    return desired


def validate_offering_context(
    db: Session,
    *,
    academic_module_id: int,
    intake_id: int,
    batch_id: int,
    semester_number: int,
    section_ids: set[int],
) -> tuple[AcademicModule, Intake, Batch, list[Section]]:
    module = db.get(AcademicModule, academic_module_id)
    intake = db.get(Intake, intake_id)
    batch = db.get(Batch, batch_id)
    if module is None:
        raise HTTPException(404, "Module not found")
    if intake is None:
        raise HTTPException(404, "Intake not found")
    if batch is None:
        raise HTTPException(404, "Batch not found")
    if intake.program_id != batch.program_id:
        raise HTTPException(422, "The selected intake and batch must belong to the same program")
    if module.semester_number != semester_number:
        raise HTTPException(422, "Module does not belong to the selected semester")

    sections = list(db.scalars(select(Section).where(Section.id.in_(section_ids)))) if section_ids else []
    found_ids = {section.id for section in sections}
    missing = section_ids - found_ids
    if missing:
        raise HTTPException(404, f"Section {min(missing)} not found")
    for section in sections:
        if section.batch_id != batch_id:
            raise HTTPException(422, f"Section {section.name} does not belong to the selected batch")
        if section.intake_id is not None and section.intake_id != intake_id:
            raise HTTPException(422, f"Section {section.name} does not belong to the selected intake")
        if section.semester_number is not None and section.semester_number != semester_number:
            raise HTTPException(422, f"Section {section.name} does not belong to the selected semester")
    return module, intake, batch, sections


def resolve_active_module_offering(
    db: Session,
    *,
    module: AcademicModule,
    intake: Intake,
    semester_number: int,
    sections: list[Section],
) -> ModuleOffering:
    """Resolve the explicit active offering for a routine without creating one."""

    if not sections:
        raise HTTPException(422, "At least one section is required")
    batch_ids = {section.batch_id for section in sections}
    if len(batch_ids) != 1:
        raise HTTPException(422, "All sections in a combined class must belong to the same batch")
    batch = db.get(Batch, next(iter(batch_ids)))
    if batch is None:
        raise HTTPException(422, "The selected section batch does not exist")
    validate_offering_context(
        db,
        academic_module_id=module.id,
        intake_id=intake.id,
        batch_id=batch.id,
        semester_number=semester_number,
        section_ids={section.id for section in sections},
    )
    offering = db.scalar(
        select(ModuleOffering).where(
            ModuleOffering.academic_module_id == module.id,
            ModuleOffering.intake_id == intake.id,
            ModuleOffering.batch_id == batch.id,
            ModuleOffering.semester_number == semester_number,
            ModuleOffering.is_active.is_(True),
        )
    )
    semester_label = f"Semester {semester_number}"
    if offering is None:
        raise HTTPException(
            422,
            f"No active module offering exists for {module.code}, {intake.name} ({intake.code}), "
            f"Batch {batch.name}, {semester_label}. Create the offering and include "
            f"{', '.join(section.name for section in sections)}.",
        )
    members = offering_section_ids(db, offering)
    missing = [section.name for section in sections if section.id not in members]
    if missing:
        names = ", ".join(missing)
        raise HTTPException(
            422,
            f"Section {names} exists but is not included in the active Module Offering for {module.code}. "
            "It is not part of the active module offering.",
        )
    return offering


def routine_section_ids(db: Session, routine: RoutineEntry) -> set[int]:
    linked = set(db.scalars(select(RoutineEntrySection.section_id).where(RoutineEntrySection.routine_entry_id == routine.id)))
    return linked or {routine.section_id}


def validate_routine_entry_module_offering(db: Session, routine: RoutineEntry, offering: ModuleOffering | None = None) -> None:
    """Raise a clear validation error unless a routine is fully contained by its offering."""

    offering = offering or routine.module_offering
    if offering is None:
        raise HTTPException(422, "Routine entry is not linked to a module offering")
    if routine.module_id != offering.academic_module_id:
        raise HTTPException(422, "Routine module does not match its module offering")
    if routine.intake_id != offering.intake_id:
        raise HTTPException(422, "Routine intake does not match its module offering")
    if routine.semester_number != offering.semester_number:
        raise HTTPException(422, "Routine semester does not match its module offering")
    allowed_sections = offering_section_ids(db, offering)
    for section_id in routine_section_ids(db, routine):
        section = db.get(Section, section_id)
        if section is None or section.batch_id != offering.batch_id or section_id not in allowed_sections:
            raise HTTPException(422, "Routine sections must belong to the linked module offering")
