from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import AcademicModule, Batch, CohortSemester, Intake, ModuleOffering, RoutineEntry, RoutineEntrySection, Section


def offering_section_ids(db: Session, offering: ModuleOffering) -> set[int]:
    return set(db.scalars(select(Section.id).join(Section.module_offerings).where(ModuleOffering.id == offering.id)))


def cohort_sections(
    db: Session,
    *,
    intake_id: int,
    batch_id: int,
    semester_number: int,
    cohort_semester_id: int | None = None,
) -> list[Section]:
    """Return the permanent sections owned by an offering's batch."""

    return list(db.scalars(
        select(Section)
        .where(Section.batch_id == batch_id)
        .order_by(Section.name, Section.id)
    ))


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


def synchronize_offering_sections(
    db: Session,
    offering: ModuleOffering,
    requested_section_ids: set[int] | None = None,
) -> list[Section]:
    """Keep offering membership inside its cohort, honoring explicit sections."""

    sections = cohort_sections(
        db,
        intake_id=offering.intake_id,
        batch_id=offering.batch_id,
        semester_number=offering.semester_number,
        cohort_semester_id=offering.cohort_semester_id,
    )
    available_ids = {section.id for section in sections}
    if requested_section_ids is not None:
        missing = requested_section_ids - available_ids
        if missing:
            raise HTTPException(422, f"Section {min(missing)} does not belong to the selected batch")
        sections = [section for section in sections if section.id in requested_section_ids]
    requested_ids = {section.id for section in sections}
    for section_id in offering_section_ids(db, offering) - requested_ids:
        if routine_uses_offering_section(db, offering.id, section_id):
            section = db.get(Section, section_id)
            raise HTTPException(
                409,
                f"Section {section.name if section else section_id} cannot leave this batch because an existing routine uses it",
            )
    offering.sections[:] = sections
    db.flush()
    return sections


def synchronize_section_module_offerings(db: Session, section: Section) -> list[ModuleOffering]:
    """Keep existing offering memberships valid when a section changes identity.

    New sections are not silently added to existing offerings: membership is an
    explicit course-assignment decision and must remain historical.
    """

    current = list(section.module_offerings)
    desired = [offering for offering in current if offering.batch_id == section.batch_id]
    inherited_query = select(ModuleOffering).where(
        ModuleOffering.inherit_all_sections.is_(True),
        ModuleOffering.batch_id == section.batch_id,
    )
    for offering in db.scalars(inherited_query):
        if offering not in desired:
            desired.append(offering)
    desired_ids = {offering.id for offering in desired}
    for offering in current:
        if offering.id not in desired_ids and routine_uses_offering_section(db, offering.id, section.id):
            raise HTTPException(
                409,
                f"Section {section.name} cannot move to a different batch because an existing routine uses it",
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
    cohort_semester_id: int | None = None,
    section_ids: set[int],
) -> tuple[AcademicModule, Intake, Batch, list[Section]]:
    module = db.get(AcademicModule, academic_module_id)
    intake = db.get(Intake, intake_id)
    batch = db.get(Batch, batch_id)
    if module is None:
        raise HTTPException(404, "Course not found")
    if intake is None:
        raise HTTPException(404, "Intake not found")
    if batch is None:
        raise HTTPException(404, "Batch not found")
    if intake.program_id != batch.program_id:
        raise HTTPException(422, "The selected intake and batch must belong to the same program")
    period = db.get(CohortSemester, cohort_semester_id) if cohort_semester_id is not None else None
    if cohort_semester_id is not None and period is None:
        raise HTTPException(404, "Semester not found")
    if period is not None and (
        period.intake_id != intake_id
        or period.batch_id != batch_id
        or period.semester_number != semester_number
    ):
        raise HTTPException(422, "Selected semester does not match the chosen Level / Intake and Batch")

    sections = list(db.scalars(select(Section).where(Section.id.in_(section_ids)))) if section_ids else []
    found_ids = {section.id for section in sections}
    missing = section_ids - found_ids
    if missing:
        raise HTTPException(404, f"Section {min(missing)} not found")
    for section in sections:
        if section.batch_id != batch_id:
            raise HTTPException(422, f"Section {section.name} does not belong to the selected batch")
    return module, intake, batch, sections


def resolve_active_module_offering(
    db: Session,
    *,
    module: AcademicModule,
    intake: Intake,
    semester_number: int,
    sections: list[Section],
    cohort_semester_id: int | None = None,
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
        cohort_semester_id=cohort_semester_id,
        section_ids={section.id for section in sections},
    )
    filters = [
        ModuleOffering.academic_module_id == module.id,
        ModuleOffering.batch_id == batch.id,
        ModuleOffering.is_active.is_(True),
    ]
    if cohort_semester_id is not None:
        filters.append(ModuleOffering.cohort_semester_id == cohort_semester_id)
    else:
        filters.extend((
            ModuleOffering.intake_id == intake.id,
            ModuleOffering.semester_number == semester_number,
        ))
    offering = db.scalar(select(ModuleOffering).where(*filters))
    semester_label = f"Semester {semester_number}"
    if offering is None:
        raise HTTPException(
            422,
            f"No active course assignment exists for {module.code}, {intake.name or intake.code} ({intake.code}), "
            f"Batch {batch.name}, {semester_label}. Create the course assignment and include "
            f"{', '.join(section.name for section in sections)}.",
        )
    members = offering_section_ids(db, offering)
    missing = [section.name for section in sections if section.id not in members]
    if missing:
        names = ", ".join(missing)
        raise HTTPException(
            422,
            f"Section {names} exists but is not included in the active Course Assignment for {module.code}. "
            "It is not part of the active course assignment.",
        )
    return offering


def routine_section_ids(db: Session, routine: RoutineEntry) -> set[int]:
    linked = set(db.scalars(select(RoutineEntrySection.section_id).where(RoutineEntrySection.routine_entry_id == routine.id)))
    return linked or {routine.section_id}


def validate_routine_entry_module_offering(db: Session, routine: RoutineEntry, offering: ModuleOffering | None = None) -> None:
    """Raise a clear validation error unless a routine is fully contained by its offering."""

    offering = offering or routine.module_offering
    if offering is None:
        raise HTTPException(422, "Routine entry is not linked to a course assignment")
    if routine.module_id != offering.academic_module_id:
        raise HTTPException(422, "Routine course does not match its course assignment")
    if routine.intake_id != offering.intake_id:
        raise HTTPException(422, "Routine Level / Intake does not match its course assignment")
    if routine.semester_number != offering.semester_number:
        raise HTTPException(422, "Routine semester does not match its course assignment")
    if offering.cohort_semester_id is not None:
        period = db.get(CohortSemester, offering.cohort_semester_id)
        if period is None or (
            period.intake_id != offering.intake_id
            or period.batch_id != offering.batch_id
            or period.semester_number != offering.semester_number
        ):
            raise HTTPException(422, "Course assignment semester context is inconsistent")
        if routine.cohort_semester_id not in (None, period.id):
            raise HTTPException(422, "Routine semester does not match its course assignment")
    allowed_sections = offering_section_ids(db, offering)
    for section_id in routine_section_ids(db, routine):
        section = db.get(Section, section_id)
        if section is None or section.batch_id != offering.batch_id or section_id not in allowed_sections:
            raise HTTPException(422, "Routine sections must belong to the linked course assignment")
