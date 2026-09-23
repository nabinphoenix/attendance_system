from collections import Counter
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.main import app
from app.modules.academic.models import (
    AcademicCalendar,
    Batch,
    BatchLevel,
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
    apply_initial_assignment,
    apply_promotion,
    move_student_section,
    placement_signature,
    preview_initial_assignment,
    preview_promotion,
    process_due_promotions,
    release_held_student,
    student_section_at,
    students_for_sections_as_of,
)
from app.modules.identity.models import User, UserRole


def setup_promotion_db(*, enroll_source: bool = True):
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    with session_factory() as db:
        admin = User(
            name='Admin',
            email='promotion-admin@example.com',
            password_hash='not-used',
            role=UserRole.ADMIN,
        )
        program = Program(name='Promotion Program')
        db.add_all([admin, program])
        db.flush()
        batch = Batch(
            name='2026-2028',
            program_id=program.id,
            start_date=date(2026, 1, 1),
            end_date=date(2028, 12, 31),
        )
        intakes = [
            Intake(name=None, code='L1-2026', program_id=program.id),
            Intake(name=None, code='L2-2026', program_id=program.id),
            Intake(name=None, code='L3-2027', program_id=program.id),
        ]
        db.add_all([batch, *intakes])
        db.flush()
        levels = [
            BatchLevel(batch_id=batch.id, level_number=index, intake_id=intake.id)
            for index, intake in enumerate(intakes, 1)
        ]
        db.add_all(levels)
        db.flush()
        dates = [
            (date(2026, 1, 1), date(2026, 3, 31)),
            (date(2026, 4, 1), date(2026, 6, 30)),
            (date(2026, 7, 1), date(2026, 9, 30)),
            (date(2026, 10, 1), date(2026, 12, 31)),
            (date(2027, 1, 1), date(2027, 3, 31)),
            (date(2027, 4, 1), date(2027, 6, 30)),
        ]
        semesters = []
        for semester_number, (start_date, end_date) in enumerate(dates, 1):
            level = levels[(semester_number - 1) // 2]
            semester = CohortSemester(
                batch_level_id=level.id,
                intake_id=level.intake_id,
                batch_id=batch.id,
                semester_number=semester_number,
                start_date=start_date,
                end_date=end_date,
            )
            semesters.append(semester)
        db.add_all(semesters)
        db.flush()
        for semester in (semesters[0], semesters[2]):
            db.add(AcademicCalendar(
                cohort_semester_id=semester.id,
                filename=f'semester-{semester.semester_number}.pdf',
                pdf_data=b'%PDF-test',
                size_bytes=9,
                uploaded_by=admin.id,
            ))
        sections = [
            Section(name='North', batch_id=batch.id),
            Section(name='South', batch_id=batch.id),
            Section(name='Studio', batch_id=batch.id),
        ]
        db.add_all(sections)
        db.flush()
        students = [
            Student(section_id=sections[index % 2].id, roll_number=f'PROMO-{index + 1}', name=f'Student {index + 1}')
            for index in range(5)
        ]
        db.add_all(students)
        db.flush()
        if enroll_source:
            db.add_all([
                StudentEnrollment(
                    student_id=student.id,
                    section_id=student.section_id,
                    cohort_semester_id=semesters[1].id,
                    starts_on=semesters[1].start_date,
                )
                for student in students[:2]
            ])
        db.commit()
        return session_factory, {
            'admin': admin.id,
            'batch': batch.id,
            'intakes': [item.id for item in intakes],
            'levels': [item.id for item in levels],
            'semesters': [item.id for item in semesters],
            'sections': [item.id for item in sections],
            'students': [item.id for item in students],
        }


def test_level_progression_preserves_history_and_supports_hold_release():
    factory, ids = setup_promotion_db()
    try:
        with factory() as db:
            source = db.get(CohortSemester, ids['semesters'][1])
            target = db.get(CohortSemester, ids['semesters'][2])
            north, south, _ = ids['sections']
            first, second = ids['students'][:2]
            source, target, rows, errors = preview_promotion(
                db,
                intake_id=source.intake_id,
                batch_id=ids['batch'],
                from_cohort_semester_id=source.id,
                to_cohort_semester_id=target.id,
                effective_date=target.start_date,
                section_mapping={north: north, south: south},
                hold_student_ids={second},
                placement_strategy='whole_section',
            )
            assert not errors
            assert source.intake_id != target.intake_id
            assert [(row.student.id, row.action) for row in rows] == [
                (first, 'promote'),
                (second, 'hold'),
            ]
            signature = placement_signature(source, target, rows)
            run, applied = apply_promotion(
                db,
                intake_id=source.intake_id,
                batch_id=ids['batch'],
                from_cohort_semester_id=source.id,
                to_cohort_semester_id=target.id,
                effective_date=target.start_date,
                section_mapping={north: north, south: south},
                hold_student_ids={second},
                placement_strategy='whole_section',
                preview_signature=signature,
            )
            db.commit()
            assert len(applied) == 2
            assert len(db.scalars(select(PromotionRunItem)).all()) == 2
            assert student_section_at(db, first, date(2026, 6, 30)) == north
            assert student_section_at(db, first, date(2026, 7, 1)) == north
            assert student_section_at(db, second, date(2026, 7, 1)) == south
            target_students = db.scalars(
                select(StudentEnrollment.student_id).where(
                    StudentEnrollment.cohort_semester_id == target.id,
                    StudentEnrollment.ends_on.is_(None),
                )
            ).all()
            assert target_students == [first]
            held_source = db.scalar(
                select(StudentEnrollment).where(
                    StudentEnrollment.student_id == second,
                    StudentEnrollment.cohort_semester_id == source.id,
                )
            )
            assert held_source.status == 'held'

            release_held_student(db, run, second, north, 'Approved after review')
            db.commit()
            assert student_section_at(db, second, date(2026, 7, 1)) == north
            history = db.scalars(
                select(StudentEnrollment)
                .where(StudentEnrollment.student_id == second)
                .order_by(StudentEnrollment.starts_on)
            ).all()
            assert [(item.cohort_semester_id, item.ends_on) for item in history] == [
                (source.id, target.start_date),
                (target.id, None),
            ]
    finally:
        app.dependency_overrides.clear()


def test_progression_requires_target_calendar_and_preview_signature():
    factory, ids = setup_promotion_db()
    with factory() as db:
        source = db.get(CohortSemester, ids['semesters'][1])
        target = db.get(CohortSemester, ids['semesters'][2])
        db.delete(db.scalar(select(AcademicCalendar).where(AcademicCalendar.cohort_semester_id == target.id)))
        db.flush()
        with pytest.raises(PromotionValidationError, match='Academic Calendar PDF'):
            preview_promotion(
                db,
                intake_id=source.intake_id,
                batch_id=ids['batch'],
                from_cohort_semester_id=source.id,
                to_cohort_semester_id=target.id,
                effective_date=target.start_date,
                section_mapping={},
                hold_student_ids=set(),
                placement_strategy='keep_existing',
            )

        db.rollback()
        source, target, rows, errors = preview_promotion(
            db,
            intake_id=source.intake_id,
            batch_id=ids['batch'],
            from_cohort_semester_id=source.id,
            to_cohort_semester_id=target.id,
            effective_date=target.start_date,
            section_mapping={},
            hold_student_ids=set(),
            placement_strategy='keep_existing',
        )
        assert not errors
        with pytest.raises(PromotionValidationError, match='roster changed'):
            apply_promotion(
                db,
                intake_id=source.intake_id,
                batch_id=ids['batch'],
                from_cohort_semester_id=source.id,
                to_cohort_semester_id=target.id,
                effective_date=target.start_date,
                section_mapping={},
                hold_student_ids=set(),
                placement_strategy='keep_existing',
                preview_signature='stale-preview',
            )


def test_initial_random_assignment_is_balanced_previewed_and_manually_overridable():
    factory, ids = setup_promotion_db(enroll_source=False)
    with factory() as db:
        semester = db.get(CohortSemester, ids['semesters'][0])
        north, south, _ = ids['sections']
        first, *_, held = ids['students']
        target, rows, errors = preview_initial_assignment(
            db,
            cohort_semester_id=semester.id,
            student_ids=set(ids['students']),
            placement_strategy='random_balanced',
            target_section_ids={north, south},
            section_mapping={},
            manual_overrides={first: south},
            hold_student_ids={held},
            random_seed=42,
        )
        assert not errors
        assert next(row for row in rows if row.student.id == first).target_section_id == south
        assert next(row for row in rows if row.student.id == held).action == 'hold'
        counts = Counter(row.target_section_id for row in rows if row.action == 'assign')
        assert max(counts.values()) - min(counts.values()) <= 1
        signature = placement_signature(target, target, rows)
        _, applied = apply_initial_assignment(
            db,
            cohort_semester_id=semester.id,
            student_ids=set(ids['students']),
            placement_strategy='random_balanced',
            target_section_ids={north, south},
            section_mapping={},
            manual_overrides={first: south},
            hold_student_ids={held},
            random_seed=42,
            preview_signature=signature,
        )
        db.commit()
        assert sum(item.action == 'assign' for item in applied) == 4
        assert db.scalar(select(StudentEnrollment.id).where(StudentEnrollment.student_id == held)) is None
        _, rerun_rows, rerun_errors = preview_initial_assignment(
            db,
            cohort_semester_id=semester.id,
            student_ids=None,
            placement_strategy='keep_existing',
            target_section_ids={north, south},
            section_mapping={},
            manual_overrides={},
            hold_student_ids=set(),
        )
        assert not rerun_errors
        assert [item.student.id for item in rerun_rows] == [held]


def test_individual_section_move_preserves_same_semester_history():
    factory, ids = setup_promotion_db(enroll_source=False)
    with factory() as db:
        semester = db.get(CohortSemester, ids['semesters'][0])
        student_id = ids['students'][0]
        north, south, _ = ids['sections']
        target, rows, errors = preview_initial_assignment(
            db,
            cohort_semester_id=semester.id,
            student_ids={student_id},
            placement_strategy='keep_existing',
            target_section_ids={north, south},
            section_mapping={},
            manual_overrides={},
            hold_student_ids=set(),
        )
        assert not errors
        apply_initial_assignment(
            db,
            cohort_semester_id=semester.id,
            student_ids={student_id},
            placement_strategy='keep_existing',
            target_section_ids={north, south},
            section_mapping={},
            manual_overrides={},
            hold_student_ids=set(),
            preview_signature=placement_signature(target, target, rows),
        )
        move_student_section(
            db,
            student_id=student_id,
            cohort_semester_id=semester.id,
            target_section_id=south,
            effective_date=date(2026, 2, 1),
        )
        db.commit()
        history = db.scalars(
            select(StudentEnrollment)
            .where(StudentEnrollment.student_id == student_id)
            .order_by(StudentEnrollment.starts_on)
        ).all()
        assert [(item.section_id, item.starts_on, item.ends_on) for item in history] == [
            (north, date(2026, 1, 1), date(2026, 2, 1)),
            (south, date(2026, 2, 1), None),
        ]


def test_due_processor_promotes_same_sections_when_target_is_ready():
    factory, ids = setup_promotion_db()
    with factory() as db:
        assert process_due_promotions(db, date(2026, 7, 1)) == 1
        north, south, _ = ids['sections']
        first, second = ids['students'][:2]
        assert student_section_at(db, first, date(2026, 7, 1)) == north
        assert student_section_at(db, second, date(2026, 7, 1)) == south
