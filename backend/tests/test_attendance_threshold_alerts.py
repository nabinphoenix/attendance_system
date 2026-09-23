from datetime import date, time, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.academic.models import (
    AcademicModule,
    Batch,
    Block,
    ClassType,
    Intake,
    ModuleOffering,
    ModuleOfferingSection,
    Program,
    Room,
    RoutineEntry,
    Section,
    Student,
    Teacher,
    TimeSlot,
)
from app.modules.analytics.service import evaluate_saved_session, run_risk_evaluations
from app.modules.attendance.models import AttendanceMethod, AttendanceRecord, AttendanceStatus
from app.modules.crm.models import AttendanceThresholdAlert, AttendanceThresholdAlertStatus
from app.modules.identity.models import User, UserRole
from app.modules.operations.models import Notification, NotificationStatus
from app.modules.scheduling.models import ClassSession, SessionStatus
from app.workers.jobs import notification_job


def threshold_environment():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    with Session() as db:
        program = Program(name="BCA")
        db.add(program)
        db.flush()
        batch = Batch(name="2026", program_id=program.id)
        intake = Intake(name="January 2026", code="JAN26", start_date=date(2026, 1, 1), program_id=program.id)
        db.add_all([batch, intake])
        db.flush()
        section = Section(name="A", batch_id=batch.id, intake_id=intake.id, semester_number=6)
        block = Block(name="Block A")
        class_type = ClassType(name="Lecture")
        slot = TimeSlot(start_time=time(9), end_time=time(10), duration_label="1 hour")
        db.add_all([section, block, class_type, slot])
        db.flush()
        room = Room(block_id=block.id, name="R1", room_type="classroom", capacity=40)
        admin = User(name="Admin", email="admin@example.com", password_hash="unused", role=UserRole.ADMIN)
        teacher_user = User(name="Teacher", email="teacher@example.com", password_hash="unused", role=UserRole.TEACHER)
        student_user = User(name="Aakriti", email="aakriti@example.com", password_hash="unused", role=UserRole.STUDENT)
        db.add_all([room, admin, teacher_user, student_user])
        db.flush()
        teacher = Teacher(user_id=teacher_user.id, employee_code="T-1")
        student = Student(user_id=student_user.id, section_id=section.id, roll_number="A-1")
        database = AcademicModule(code="DB601", title="Advanced Database Systems", credits=3, semester_number=6)
        cloud = AcademicModule(code="CL601", title="Cloud Infrastructure and Services", credits=3, semester_number=6)
        db.add_all([teacher, student, database, cloud])
        db.flush()

        database_offering = ModuleOffering(
            academic_module_id=database.id,
            intake_id=intake.id,
            batch_id=batch.id,
            semester_number=6,
        )
        cloud_offering = ModuleOffering(
            academic_module_id=cloud.id,
            intake_id=intake.id,
            batch_id=batch.id,
            semester_number=6,
        )
        db.add_all([database_offering, cloud_offering])
        db.flush()
        db.add_all(
            [
                ModuleOfferingSection(module_offering_id=database_offering.id, section_id=section.id),
                ModuleOfferingSection(module_offering_id=cloud_offering.id, section_id=section.id),
            ]
        )
        database_routine = RoutineEntry(
            intake_id=intake.id,
            semester_number=6,
            section_id=section.id,
            module_id=database.id,
            module_offering_id=database_offering.id,
            class_type_id=class_type.id,
            teacher_id=teacher.id,
            room_id=room.id,
            day_of_week=0,
            time_slot_id=slot.id,
        )
        cloud_routine = RoutineEntry(
            intake_id=intake.id,
            semester_number=6,
            section_id=section.id,
            module_id=cloud.id,
            module_offering_id=cloud_offering.id,
            class_type_id=class_type.id,
            teacher_id=teacher.id,
            room_id=room.id,
            day_of_week=1,
            time_slot_id=slot.id,
        )
        db.add_all([database_routine, cloud_routine])
        db.flush()

        def completed_session(routine, offset, status):
            session = ClassSession(
                routine_entry_id=routine.id,
                session_date=date.today() - timedelta(days=offset),
                effective_teacher_id=teacher.id,
                effective_room="R1",
                status=SessionStatus.COMPLETED,
            )
            db.add(session)
            db.flush()
            db.add(
                AttendanceRecord(
                    class_session_id=session.id,
                    student_id=student.id,
                    status=status,
                    method=AttendanceMethod.FINALIZATION,
                )
            )
            return session

        # Database attendance is exactly 75%, Cloud attendance is 25%.
        database_sessions = [
            completed_session(database_routine, offset, status)
            for offset, status in enumerate(
                [AttendanceStatus.PRESENT, AttendanceStatus.PRESENT, AttendanceStatus.PRESENT, AttendanceStatus.ABSENT],
                start=1,
            )
        ]
        cloud_sessions = [
            completed_session(cloud_routine, offset + 10, status)
            for offset, status in enumerate(
                [AttendanceStatus.PRESENT, AttendanceStatus.ABSENT, AttendanceStatus.ABSENT, AttendanceStatus.ABSENT],
                start=1,
            )
        ]
        db.commit()
        return Session, {
            "admin_id": admin.id,
            "student_id": student.id,
            "cloud_offering_id": cloud_offering.id,
            "database_offering_id": database_offering.id,
            "cloud_sessions": [session.id for session in cloud_sessions],
            "database_sessions": [session.id for session in database_sessions],
        }


def test_threshold_is_per_module_offering_and_realerts_only_after_recovery():
    Session, ids = threshold_environment()
    with Session() as db:
        first = evaluate_saved_session(
            db,
            ids["cloud_sessions"][-1],
            actor_id=ids["admin_id"],
        )
        alerts = list(db.scalars(select(AttendanceThresholdAlert)).all())
        notifications = list(db.scalars(select(Notification)).all())

        assert first["created"] == 1
        assert len(alerts) == 1
        assert alerts[0].module_offering_id == ids["cloud_offering_id"]
        assert alerts[0].percentage_at_trigger == 25
        assert alerts[0].attended_sessions == 1
        assert alerts[0].eligible_sessions == 4
        assert len(notifications) == 1
        assert "Cloud Infrastructure and Services" in notifications[0].subject

        # Evaluating an unrelated module at exactly 75% does not create an alert.
        database = evaluate_saved_session(
            db,
            ids["database_sessions"][-1],
            actor_id=ids["admin_id"],
        )
        assert database["triggered"] == 0
        assert len(list(db.scalars(select(AttendanceThresholdAlert)).all())) == 1

        # Re-evaluating while still below the threshold never queues a duplicate.
        repeat = evaluate_saved_session(
            db,
            ids["cloud_sessions"][0],
            actor_id=ids["admin_id"],
        )
        assert repeat["updated"] == 1
        assert len(list(db.scalars(select(Notification)).all())) == 1

        cloud_records = list(
            db.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.class_session_id.in_(ids["cloud_sessions"])
                )
            ).all()
        )
        for record in cloud_records:
            record.status = AttendanceStatus.PRESENT
        db.commit()

        recovered = evaluate_saved_session(
            db,
            ids["cloud_sessions"][-1],
            actor_id=ids["admin_id"],
        )
        assert recovered["resolved"] == 1
        assert db.scalar(select(AttendanceThresholdAlert).where(AttendanceThresholdAlert.status == AttendanceThresholdAlertStatus.ACTIVE)) is None

        cloud_records[0].status = AttendanceStatus.ABSENT
        cloud_records[1].status = AttendanceStatus.ABSENT
        db.commit()
        reentered = evaluate_saved_session(
            db,
            ids["cloud_sessions"][-1],
            actor_id=ids["admin_id"],
        )
        assert reentered["created"] == 1
        assert len(list(db.scalars(select(Notification)).all())) == 2
        assert len(list(db.scalars(select(AttendanceThresholdAlert)).all())) == 2


def test_bulk_recalculation_records_existing_low_state_without_email_backfill():
    Session, ids = threshold_environment()
    with Session() as db:
        result = run_risk_evaluations(db, actor_id=ids["admin_id"])
        alert = db.scalar(select(AttendanceThresholdAlert))

        assert result["created"] == 1
        assert alert is not None
        assert alert.notification_id is None
        assert list(db.scalars(select(Notification)).all()) == []


def test_missing_email_marks_delivery_failed_without_changing_attendance(monkeypatch):
    Session, ids = threshold_environment()
    with Session() as db:
        evaluate_saved_session(db, ids["cloud_sessions"][-1], actor_id=ids["admin_id"])
        alert = db.scalar(select(AttendanceThresholdAlert))
        notification = db.scalar(select(Notification))
        student = db.get(Student, ids["student_id"])
        records_before = [
            record.status
            for record in db.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.class_session_id.in_(ids["cloud_sessions"])
                )
            ).all()
        ]

        student.user_id = None
        student.email = None
        db.commit()
        monkeypatch.setattr(notification_job.settings, "smtp_host", "smtp.example.test")
        notification_job.deliver_notification(db, notification)
        db.commit()

        assert notification.status == NotificationStatus.FAILED
        assert notification.delivery_attempts == 1
        assert notification.failure_reason == "Recipient has no deliverable email address"
        assert alert.email_failed_at is not None
        records_after = [
            record.status
            for record in db.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.class_session_id.in_(ids["cloud_sessions"])
                )
            ).all()
        ]
        assert records_after == records_before
