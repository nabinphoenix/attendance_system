from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.main import app
from app.modules.academic.models import (
    Batch,
    CohortSemester,
    Intake,
    Program,
    PromotionRunItem,
    Section,
    Student,
    StudentEnrollment,
)
from app.modules.academic.promotion_service import (
    PromotionValidationError,
    apply_promotion,
    preview_promotion,
    student_section_at,
    students_for_sections_as_of,
    process_due_promotions,
)
from app.core.database import get_db


def setup_promotion_db():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with session_factory() as db:
        program = Program(name='Promotion Program')
        db.add(program)
        db.flush()
        batch = Batch(name='Promotion Batch', program_id=program.id)
        intake = Intake(
            name='September Intake',
            code='SEP-PROMO',
            start_date=date(2026, 1, 1),
            program_id=program.id,
        )
        other_intake = Intake(
            name='January Intake',
            code='JAN-PROMO',
            start_date=date(2026, 1, 1),
            program_id=program.id,
        )
        db.add_all([batch, intake, other_intake])
        db.flush()
        source = CohortSemester(
            intake_id=intake.id,
            batch_id=batch.id,
            semester_number=2,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )
        target = CohortSemester(
            intake_id=intake.id,
            batch_id=batch.id,
            semester_number=3,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
        )
        concurrent = CohortSemester(
            intake_id=other_intake.id,
            batch_id=batch.id,
            semester_number=2,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 4, 30),
        )
        db.add_all([source, target, concurrent])
        db.flush()
        source_a = Section(
            name='A',
            batch_id=batch.id,
            intake_id=intake.id,
            semester_number=2,
        )
        source_b = Section(
            name='B',
            batch_id=batch.id,
            intake_id=intake.id,
            semester_number=2,
        )
        target_a = Section(
            name='A',
            batch_id=batch.id,
            intake_id=intake.id,
            semester_number=3,
        )
        target_b = Section(
            name='B',
            batch_id=batch.id,
            intake_id=intake.id,
            semester_number=3,
        )
        db.add_all([source_a, source_b, target_a, target_b])
        db.flush()
        first = Student(section_id=source_a.id, roll_number='PROMO-1', name='First Student')
        second = Student(section_id=source_b.id, roll_number='PROMO-2', name='Held Student')
        db.add_all([first, second])
        db.flush()
        db.add_all(
            [
                StudentEnrollment(
                    student_id=first.id,
                    section_id=source_a.id,
                    cohort_semester_id=source.id,
                    starts_on=source.start_date,
                ),
                StudentEnrollment(
                    student_id=second.id,
                    section_id=source_b.id,
                    cohort_semester_id=source.id,
                    starts_on=source.start_date,
                ),
            ]
        )
        db.commit()
        return session_factory, source.id, target.id, source_a.id, source_b.id, target_a.id, target_b.id, first.id, second.id


def test_concurrent_intakes_can_share_a_semester_number_and_promotion_preserves_history():
    session_factory, source_id, target_id, source_a, source_b, target_a, target_b, first_id, second_id = setup_promotion_db()
    try:
        with session_factory() as db:
            source, target, rows, errors = preview_promotion(
                db,
                intake_id=db.get(CohortSemester, source_id).intake_id,
                batch_id=db.get(CohortSemester, source_id).batch_id,
                from_cohort_semester_id=source_id,
                to_cohort_semester_id=target_id,
                effective_date=date(2026, 4, 1),
                section_mapping={source_a: target_a, source_b: target_b},
                hold_student_ids={second_id},
            )
            assert source.semester_number == 2
            assert target.semester_number == 3
            assert not errors
            assert [(row.student.id, row.action) for row in rows] == [
                (first_id, 'promote'),
                (second_id, 'hold'),
            ]
            run, applied_rows = apply_promotion(
                db,
                intake_id=source.intake_id,
                batch_id=source.batch_id,
                from_cohort_semester_id=source_id,
                to_cohort_semester_id=target_id,
                effective_date=date(2026, 4, 1),
                section_mapping={source_a: target_a, source_b: target_b},
                hold_student_ids={second_id},
            )
            db.commit()
            assert len(applied_rows) == 2
            assert len(db.scalars(select(PromotionRunItem)).all()) == 2
            assert student_section_at(db, first_id, date(2026, 3, 31)) == source_a
            assert student_section_at(db, first_id, date(2026, 4, 1)) == target_a
            assert student_section_at(db, second_id, date(2026, 4, 1)) == source_b
            assert len(students_for_sections_as_of(db, {source_a}, date(2026, 3, 31))) == 1
            assert len(students_for_sections_as_of(db, {target_a}, date(2026, 4, 1))) == 1
            history = db.scalars(
                select(StudentEnrollment).where(StudentEnrollment.student_id == first_id)
            ).all()
            assert [(item.starts_on, item.ends_on) for item in history] == [
                (date(2026, 1, 1), date(2026, 4, 1)),
                (date(2026, 4, 1), None),
            ]
    finally:
        app.dependency_overrides.clear()


def test_promotion_rejects_non_adjacent_or_mismatched_dates():
    session_factory, source_id, target_id, source_a, _, target_a, _, _, _ = setup_promotion_db()
    try:
        with session_factory() as db:
            source = db.get(CohortSemester, source_id)
            try:
                apply_promotion(
                    db,
                    intake_id=source.intake_id,
                    batch_id=source.batch_id,
                    from_cohort_semester_id=source_id,
                    to_cohort_semester_id=target_id,
                    effective_date=date(2026, 4, 2),
                    section_mapping={source_a: target_a},
                    hold_student_ids=set(),
                )
            except PromotionValidationError as exc:
                assert 'target start date' in str(exc).lower()
            else:
                raise AssertionError('Expected an invalid target date to be rejected')
    finally:
        app.dependency_overrides.clear()


def test_promotion_keeps_batch_when_target_intake_changes():
    session_factory, source_id, _, source_a, source_b, _, _, first_id, _ = setup_promotion_db()
    try:
        with session_factory() as db:
            source = db.get(CohortSemester, source_id)
            target_intake = db.scalars(select(Intake).where(Intake.code == 'JAN-PROMO')).one()
            target = CohortSemester(
                intake_id=target_intake.id,
                batch_id=source.batch_id,
                semester_number=3,
                start_date=date(2026, 4, 1),
                end_date=date(2026, 6, 30),
            )
            db.add(target)
            db.flush()
            target_section = Section(
                name='A',
                batch_id=source.batch_id,
                intake_id=target_intake.id,
                semester_number=3,
                cohort_semester_id=target.id,
            )
            target_section_b = Section(
                name='B',
                batch_id=source.batch_id,
                intake_id=target_intake.id,
                semester_number=3,
                cohort_semester_id=target.id,
            )
            db.add_all([target_section, target_section_b])
            db.commit()

            run, _ = apply_promotion(
                db,
                intake_id=source.intake_id,
                batch_id=source.batch_id,
                from_cohort_semester_id=source.id,
                to_cohort_semester_id=target.id,
                effective_date=target.start_date,
                section_mapping={source_a: target_section.id, source_b: target_section_b.id},
                hold_student_ids=set(),
            )
            db.commit()

            assert run.intake_id == source.intake_id
            assert db.get(Student, first_id).section_id == target_section.id
            history = db.scalars(
                select(StudentEnrollment).where(StudentEnrollment.student_id == first_id)
            ).all()
            assert [item.cohort_semester_id for item in history] == [source.id, target.id]
    finally:
        app.dependency_overrides.clear()


def test_due_promotion_processor_uses_configured_same_named_sections():
    session_factory, source_id, target_id, _, _, target_a, target_b, first_id, second_id = setup_promotion_db()
    try:
        with session_factory() as db:
            assert process_due_promotions(db, date(2026, 4, 1)) == 1
            assert student_section_at(db, first_id, date(2026, 4, 1)) == target_a
            assert student_section_at(db, second_id, date(2026, 4, 1)) == target_b
    finally:
        app.dependency_overrides.clear()
