"""Allowlisted AI tools. The LLM never receives a database connection."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.academic.models import Batch, BatchLevel, Block, CohortSemester, Intake, Program, Room, Section, Student
from app.modules.academic.routine_router import effective_room_classes
from app.modules.academic.module_offering_service import synchronize_section_module_offerings
from app.modules.academic.promotion_service import PromotionValidationError, apply_promotion, placement_signature, preview_promotion, students_for_sections_as_of
from app.modules.analytics.service import subject_stats
from app.modules.identity.models import User
from app.modules.operations.service import log_audit
from .models import AgentApproval
from .read_tools import data_catalog, database_records, google_form_responses, import_history


class AgentActionError(ValueError):
    """A validation error safe to show to an administrator."""


@dataclass
class ToolOutcome:
    data: dict[str, Any]
    pending: dict[str, Any] | None = None


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    parameters: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        parameters["required"] = required
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


TOOL_DEFINITIONS = [
    _tool("get_room_availability", "Read scheduled room availability including approved overrides and cancellations. For now omit date and time; the server uses Nepal campus time. Pass block_name directly, e.g. A or Block A; no ID lookup needed.", {"block_name": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD; defaults to today in Nepal"}, "time": {"type": "string", "description": "HH:MM campus time; defaults to now"}}),
    _tool("search_academic", "Find IDs for programs, batches, intakes, sections, cohort semesters, and students. Use before actions needing IDs.", {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 25}}, ["query"]),
    _tool("get_attendance_summary", "Read attendance for exactly one student_id or section_id.", {"student_id": {"type": "integer"}, "section_id": {"type": "integer"}}),
    _tool("get_at_risk_students", "Read students below the configured attendance threshold.", {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
    _tool("create_program", "Propose a new program. It requires a confirmation and never writes immediately.", {"name": {"type": "string"}}, ["name"]),
    _tool("create_batch", "Propose a three-year batch with Level 1, 2, and 3 Intake Codes. Dates use YYYY-MM-DD.", {"name": {"type": "string"}, "program_id": {"type": "integer"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "level_1_intake_code": {"type": "string"}, "level_2_intake_code": {"type": "string"}, "level_3_intake_code": {"type": "string"}}, ["name", "program_id", "start_date", "end_date", "level_1_intake_code", "level_2_intake_code", "level_3_intake_code"]),
    _tool("create_intake", "Propose an Intake Code. The display name and start date are optional.", {"name": {"type": "string"}, "code": {"type": "string"}, "start_date": {"type": "string"}, "program_id": {"type": "integer"}}, ["code", "program_id"]),
    _tool("create_section", "Propose a permanent Section owned by a Batch.", {"name": {"type": "string"}, "batch_id": {"type": "integer"}, "combined_with": {"type": "string"}}, ["name", "batch_id"]),
    _tool("create_cohort_semester", "Propose a dated Semester for a configured Batch Level. This does not promote students.", {"batch_level_id": {"type": "integer"}, "semester_number": {"type": "integer", "minimum": 1, "maximum": 6}, "attempt_number": {"type": "integer", "minimum": 1}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "status": {"type": "string", "enum": ["planned", "active", "completed"]}}, ["batch_level_id", "semester_number", "start_date", "end_date"]),
    _tool("preview_promotion", "Preview a single intake and batch moving to its next dated semester. Search for all IDs first. A valid preview becomes an approval-only proposal.", {"intake_id": {"type": "integer"}, "batch_id": {"type": "integer"}, "from_cohort_semester_id": {"type": "integer"}, "to_cohort_semester_id": {"type": "integer"}, "effective_date": {"type": "string"}, "section_mapping": {"type": "object", "additionalProperties": {"type": "integer"}}, "hold_student_ids": {"type": "array", "items": {"type": "integer"}}, "notes": {"type": "string"}}, ["intake_id", "batch_id", "from_cohort_semester_id", "to_cohort_semester_id", "effective_date"]),
    _tool("get_database_catalog", "List every database dataset available to this administrator, its safe columns, and row count. Contact, authentication, location, token, and free-text private fields are excluded.", {}),
    _tool("read_database_records", "Read a bounded set of safe fields from one catalog dataset. Always call get_database_catalog before using a new dataset name. This is read-only and scoped to the active college.", {"dataset": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, ["dataset"]),
    _tool("get_import_history", "Read saved CSV/XLSX import outcomes. Original uploaded files are not retained; contact fields in saved row data are redacted.", {"import_job_id": {"type": "integer"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}),
    _tool("get_google_form_responses", "Read a bounded page of the configured Google Form responses. This is read-only; respondent email and sensitive answer fields are redacted.", {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
]


def execute_tool(db: Session, actor: User, name: str, arguments: dict[str, Any]) -> ToolOutcome:
    if actor.role.value not in {"admin", "super_admin"}:
        raise AgentActionError("Only an administrator can use this assistant.")
    handlers = {
        "get_room_availability": _room_availability,
        "search_academic": _search_academic,
        "get_attendance_summary": _attendance_summary,
        "get_at_risk_students": _at_risk_students,
        "get_database_catalog": _database_catalog,
        "read_database_records": _database_records,
        "get_import_history": _import_history,
        "get_google_form_responses": _google_form_responses,
        "create_program": _propose_program,
        "create_batch": _propose_batch,
        "create_intake": _propose_intake,
        "create_section": _propose_section,
        "create_cohort_semester": _propose_cohort_semester,
        "preview_promotion": _propose_promotion,
    }
    handler = handlers.get(name)
    if handler is None:
        raise AgentActionError("That action is not permitted in this assistant.")
    return handler(db, actor, arguments)


def _room_availability(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    now = datetime.now(timezone(timedelta(hours=5, minutes=45), "Asia/Kathmandu"))
    on_date = _date(args, "date") if args.get("date") is not None else now.date()
    at_time = now.time()
    if args.get("time") is not None:
        value = _string(args, "time", 5)
        try:
            if len(value) != 5 or value[2] != ":":
                raise ValueError
            at_time = time.fromisoformat(value)
        except ValueError as exc:
            raise AgentActionError("time must use HH:MM in campus time.") from exc
    block_name = _optional_string(args, "block_name", 100)
    blocks = db.scalars(select(Block).order_by(Block.name)).all()
    if block_name:
        def normalized(value: str) -> str:
            return value.strip().casefold().removeprefix("block ").strip()
        blocks = [block for block in blocks if normalized(block.name) == normalized(block_name)]
        if not blocks:
            raise AgentActionError(f"Block '{block_name}' was not found. Check the block name.")
    classes = effective_room_classes(db, on_date)
    result = []
    for block in blocks:
        rooms = []
        for room in db.scalars(select(Room).where(Room.block_id == block.id).order_by(Room.name)).all():
            bookings = [item for item in classes if not item.cancelled and item.room_id == room.id]
            current = [item for item in bookings if item.start_time <= at_time < item.end_time]
            upcoming = [item.start_time for item in bookings if item.start_time > at_time]
            rooms.append({
                "id": room.id, "name": room.name, "room_type": room.room_type, "capacity": room.capacity,
                "status": "occupied" if current else "available",
                "occupied_until": max(item.end_time for item in current).isoformat() if current else None,
                "next_class_at": min(upcoming).isoformat() if upcoming else None,
            })
        result.append({"id": block.id, "name": block.name, "rooms": rooms})
    return ToolOutcome({"date": on_date.isoformat(), "time": at_time.isoformat(), "timezone": "Asia/Kathmandu", "basis": "Scheduled classes and approved overrides; not live physical occupancy.", "blocks": result})


def _search_academic(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    query = _string(args, "query", 150)
    limit = _integer(args, "limit", 10, 1, 25)
    pattern = f"%{query}%"
    cohorts = db.execute(
        select(CohortSemester, Intake, Batch).join(Intake, CohortSemester.intake_id == Intake.id).join(Batch, CohortSemester.batch_id == Batch.id)
        .where(or_(Intake.name.ilike(pattern), Intake.code.ilike(pattern), Batch.name.ilike(pattern))).order_by(CohortSemester.start_date.desc()).limit(limit)
    ).all()
    return ToolOutcome({
        "programs": [{"id": x.id, "name": x.name} for x in db.scalars(select(Program).where(Program.name.ilike(pattern)).order_by(Program.name).limit(limit)).all()],
        "batches": [{"id": x.id, "name": x.name, "program_id": x.program_id} for x in db.scalars(select(Batch).where(Batch.name.ilike(pattern)).order_by(Batch.name).limit(limit)).all()],
        "intakes": [{"id": x.id, "name": x.name, "code": x.code, "start_date": x.start_date.isoformat() if x.start_date else None, "program_id": x.program_id} for x in db.scalars(select(Intake).where(or_(Intake.name.ilike(pattern), Intake.code.ilike(pattern))).order_by(Intake.code).limit(limit)).all()],
        "sections": [{"id": x.id, "name": x.name, "batch_id": x.batch_id} for x in db.scalars(select(Section).where(Section.name.ilike(pattern)).order_by(Section.name).limit(limit)).all()],
        "cohort_semesters": [{**_cohort_data(cohort), "intake": {"id": intake.id, "code": intake.code}, "batch": {"id": batch.id, "name": batch.name}} for cohort, intake, batch in cohorts],
        "students": [{"id": x.id, "name": _student_name(x), "roll_number": x.roll_number, "section_id": x.section_id} for x in db.scalars(select(Student).where(or_(Student.name.ilike(pattern), Student.roll_number.ilike(pattern))).order_by(Student.roll_number).limit(limit)).all()],
    })


def _attendance_summary(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    student_id, section_id = _optional_integer(args, "student_id"), _optional_integer(args, "section_id")
    if bool(student_id) == bool(section_id):
        raise AgentActionError("Provide either student_id or section_id for an attendance summary.")
    if student_id:
        student = _get(db, Student, student_id, "Student")
        stats = subject_stats(db, student.id)
        present, total = sum(x["present"] for x in stats), sum(x["total"] for x in stats)
        return ToolOutcome({"student": {"id": student.id, "name": _student_name(student), "roll_number": student.roll_number}, "present": present, "absent": total - present, "total": total, "overall_percentage": round(100 * present / total, 2) if total else 0, "subjects": stats})
    section = _get(db, Section, section_id, "Section")
    rows, present, total = [], 0, 0
    for student in students_for_sections_as_of(db, {section.id}, date.today()):
        stats = subject_stats(db, student.id)
        student_present, student_total = sum(x["present"] for x in stats), sum(x["total"] for x in stats)
        present += student_present
        total += student_total
        rows.append({"student_id": student.id, "student_name": _student_name(student), "roll_number": student.roll_number, "percentage": round(100 * student_present / student_total, 2) if student_total else 0, "observations": student_total})
    return ToolOutcome({"section": {"id": section.id, "name": section.name}, "overall_percentage": round(100 * present / total, 2) if total else 0, "students": rows})


def _at_risk_students(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    limit = _integer(args, "limit", 50, 1, 100)
    rows = []
    for student in db.scalars(select(Student).order_by(Student.roll_number)).all():
        for stat in subject_stats(db, student.id):
            if stat["total"] >= settings.minimum_observations and stat["percentage"] < settings.attendance_threshold_percent:
                rows.append({"student_id": student.id, "student_name": _student_name(student), "roll_number": student.roll_number, "subject_name": stat["subject_name"], "attendance_percentage": stat["percentage"], "observations": stat["total"]})
    rows.sort(key=lambda x: (x["attendance_percentage"], x["student_name"].lower()))
    return ToolOutcome({"threshold_percent": settings.attendance_threshold_percent, "minimum_observations": settings.minimum_observations, "students": rows[:limit], "total_matches": len(rows)})


def _propose_program(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    name = _string(args, "name", 150)
    if db.scalar(select(Program.id).where(Program.name.ilike(name))):
        raise AgentActionError("A program with that name already exists.")
    return _pending(db, actor, "create_program", {"name": name}, {"summary": f"Create program '{name}'."})


def _propose_batch(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    name, program = _string(args, "name", 100), _get(db, Program, _integer(args, "program_id", None, 1), "Program")
    if db.scalar(select(Batch.id).where(Batch.name.ilike(name), Batch.program_id == program.id)):
        raise AgentActionError("That program already has a batch with this name.")
    start_date, end_date = _date(args, 'start_date'), _date(args, 'end_date')
    if end_date != _three_year_end(start_date):
        raise AgentActionError('Batch end_date must be exactly three academic years after start_date.')
    codes = [_string(args, f'level_{level}_intake_code', 50).upper() for level in range(1, 4)]
    if len(set(codes)) != 3:
        raise AgentActionError('Each Level requires a different Intake Code.')
    payload = {"name": name, "program_id": program.id, "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "intake_codes": codes}
    return _pending(db, actor, "create_batch", payload, {"summary": f"Create three-year batch '{name}' in program '{program.name}'."})


def _propose_intake(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    name, code = _optional_string(args, "name", 100), _string(args, "code", 50).upper()
    start_date = _date(args, "start_date") if args.get('start_date') else None
    program = _get(db, Program, _integer(args, "program_id", None, 1), "Program")
    if db.scalar(select(Intake.id).where(Intake.code.ilike(code))):
        raise AgentActionError("That Intake Code already exists.")
    payload = {"name": name, "code": code, "start_date": start_date.isoformat() if start_date else None, "program_id": program.id}
    return _pending(db, actor, "create_intake", payload, {"summary": f"Create Intake Code {code} for '{program.name}'."})


def _propose_section(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    name, batch = _string(args, "name", 50), _get(db, Batch, _integer(args, "batch_id", None, 1), "Batch")
    if db.scalar(select(Section.id).where(Section.name.ilike(name), Section.batch_id == batch.id)):
        raise AgentActionError("That Section already exists in this Batch.")
    payload = {"name": name, "batch_id": batch.id, "combined_with": _optional_string(args, "combined_with", 100)}
    return _pending(db, actor, "create_section", payload, {"summary": f"Create section '{name}' in batch '{batch.name}'.", "section": payload})


def _propose_cohort_semester(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    level = _get(db, BatchLevel, _integer(args, "batch_level_id", None, 1), "Batch Level")
    batch, intake = level.batch, level.intake
    semester, attempt, start_date, end_date = _integer(args, "semester_number", None, 1), _integer(args, "attempt_number", 1, 1), _date(args, "start_date"), _date(args, "end_date")
    if semester not in {level.level_number * 2 - 1, level.level_number * 2}:
        raise AgentActionError(f'Level {level.level_number} does not contain Semester {semester}.')
    if start_date > end_date:
        raise AgentActionError("The cohort semester end date must be on or after its start date.")
    if db.scalar(select(CohortSemester.id).where(CohortSemester.intake_id == intake.id, CohortSemester.batch_id == batch.id, CohortSemester.semester_number == semester, CohortSemester.attempt_number == attempt)):
        raise AgentActionError("That intake, batch, semester, and attempt already has a dated cohort semester.")
    status = _optional_string(args, "status", 20) or "planned"
    if status not in {"planned", "active", "completed"}:
        raise AgentActionError("Cohort semester status must be planned, active, or completed.")
    payload = {"batch_level_id": level.id, "semester_number": semester, "attempt_number": attempt, "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "status": status}
    return _pending(db, actor, "create_cohort_semester", payload, {"summary": f"Create {intake.code} / {batch.name} semester {semester}: {start_date.isoformat()} to {end_date.isoformat()}.", "cohort_semester": payload})


def _propose_promotion(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    payload = {
        "intake_id": _integer(args, "intake_id", None, 1),
        "batch_id": _integer(args, "batch_id", None, 1),
        "from_cohort_semester_id": _integer(args, "from_cohort_semester_id", None, 1),
        "to_cohort_semester_id": _integer(args, "to_cohort_semester_id", None, 1),
        "effective_date": _date(args, "effective_date").isoformat(),
        "section_mapping": _section_mapping(args.get("section_mapping") or {}),
        "hold_student_ids": _integer_list(args.get("hold_student_ids") or []),
        "notes": _optional_string(args, "notes", 500),
    }
    try:
        source, target, students, errors = preview_promotion(
            db, intake_id=payload["intake_id"], batch_id=payload["batch_id"],
            from_cohort_semester_id=payload["from_cohort_semester_id"], to_cohort_semester_id=payload["to_cohort_semester_id"],
            effective_date=date.fromisoformat(payload["effective_date"]), section_mapping=payload["section_mapping"], hold_student_ids=set(payload["hold_student_ids"]),
        )
    except PromotionValidationError as exc:
        raise AgentActionError(str(exc)) from exc
    preview = {
        "source": _cohort_data(source), "target": _cohort_data(target), "total_students": len(students),
        "promote_count": sum(x.action == "promote" for x in students), "hold_count": sum(x.action == "hold" for x in students), "errors": errors,
        "students": [{"id": x.student.id, "name": _student_name(x.student), "roll_number": x.student.roll_number, "source_section_id": x.source_section_id, "target_section_id": x.target_section_id, "action": x.action, "reason": x.reason} for x in students],
    }
    if errors:
        return ToolOutcome(preview)
    payload["preview_signature"] = placement_signature(source, target, students)
    preview["preview_signature"] = payload["preview_signature"]
    preview["summary"] = f"Promote {preview['promote_count']} student(s) and hold {preview['hold_count']} student(s) from semester {source.semester_number} to semester {target.semester_number}."
    return _pending(db, actor, "apply_promotion", payload, preview)


def _pending(db: Session, actor: User, action_type: str, payload: dict[str, Any], preview: dict[str, Any]) -> ToolOutcome:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.ai_confirmation_expire_minutes)
    approval = AgentApproval(
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(), actor_id=actor.id, action_type=action_type,
        payload_json=json.dumps(payload, default=str, separators=(",", ":")), preview_json=json.dumps(preview, default=str, separators=(",", ":")), expires_at=expires_at,
    )
    db.add(approval)
    db.flush()
    log_audit(db, actor.id, "agent.action.previewed", "agent_approval", approval.id, None, {"action_type": action_type, "expires_at": expires_at.isoformat()})
    preview_data = {**preview, "action_type": action_type, "expires_at": expires_at.isoformat()}
    return ToolOutcome(preview_data, {"confirmation_token": token, "preview": preview_data, "action_type": action_type})


def confirm_approval(db: Session, actor: User, token: str, reason: str | None) -> dict[str, Any]:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    approval = db.scalar(select(AgentApproval).where(AgentApproval.token_hash == digest))
    if approval is None or approval.actor_id != actor.id or approval.status != "pending":
        raise AgentActionError("This pending approval was not found.")
    expiry = approval.expires_at if approval.expires_at.tzinfo else approval.expires_at.replace(tzinfo=UTC)
    if expiry <= datetime.now(UTC):
        raise AgentActionError("This approval has expired. Ask the assistant for a fresh preview.")
    try:
        payload = json.loads(approval.payload_json)
    except json.JSONDecodeError as exc:
        raise AgentActionError("The saved approval payload is invalid.") from exc
    result = _apply_action(db, actor, approval.action_type, payload)
    approval.status, approval.used_at = "approved", datetime.now(UTC)
    db.flush()
    log_audit(db, actor.id, "agent.action.approved", "agent_approval", approval.id, {"action_type": approval.action_type, "status": "pending"}, {"action_type": approval.action_type, "status": "approved", "reason": reason})
    return result


def cancel_approval(db: Session, actor: User, token: str) -> None:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    approval = db.scalar(select(AgentApproval).where(AgentApproval.token_hash == digest))
    if approval is None or approval.actor_id != actor.id or approval.status != "pending":
        raise AgentActionError("This pending approval was not found.")
    approval.status = "cancelled"
    db.flush()
    log_audit(db, actor.id, "agent.action.cancelled", "agent_approval", approval.id, {"action_type": approval.action_type, "status": "pending"}, {"action_type": approval.action_type, "status": "cancelled"})


def _apply_action(db: Session, actor: User, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action_type == "create_program":
        name = _string(payload, "name", 150)
        if db.scalar(select(Program.id).where(Program.name.ilike(name))):
            raise AgentActionError("A program with that name now exists.")
        item = Program(name=name)
        db.add(item); db.flush()
        log_audit(db, actor.id, "program.created", "program", item.id, None, {"name": item.name, "source": "ai_agent"})
        return {"entity": "program", "id": item.id, "name": item.name}
    if action_type == "create_batch":
        name, program = _string(payload, "name", 100), _get(db, Program, _integer(payload, "program_id", None, 1), "Program")
        if db.scalar(select(Batch.id).where(Batch.name.ilike(name), Batch.program_id == program.id)):
            raise AgentActionError("That program now has a batch with this name.")
        start_date, end_date = _date(payload, 'start_date'), _date(payload, 'end_date')
        codes = [_string({'code': code}, 'code', 50).upper() for code in payload.get('intake_codes', [])]
        if end_date != _three_year_end(start_date) or len(codes) != 3 or len(set(codes)) != 3:
            raise AgentActionError('A Batch requires exact three-year dates and three different Level Intake Codes.')
        item = Batch(name=name, program_id=program.id, start_date=start_date, end_date=end_date)
        db.add(item); db.flush()
        for level_number, code in enumerate(codes, 1):
            intake = db.scalar(select(Intake).where(Intake.code.ilike(code)))
            if intake is None:
                intake = Intake(code=code, name=None, start_date=None, program_id=program.id)
                db.add(intake); db.flush()
            elif intake.program_id != program.id:
                raise AgentActionError(f'Intake Code {code} belongs to another Program.')
            db.add(BatchLevel(batch_id=item.id, level_number=level_number, intake_id=intake.id))
        db.flush()
        log_audit(db, actor.id, "batch.created", "batch", item.id, None, {"name": item.name, "program_id": item.program_id, "source": "ai_agent"})
        return {"entity": "batch", "id": item.id, "name": item.name, "program_id": item.program_id}
    if action_type == "create_intake":
        name, code = _optional_string(payload, "name", 100), _string(payload, "code", 50).upper()
        start_date = _date(payload, "start_date") if payload.get('start_date') else None
        program = _get(db, Program, _integer(payload, "program_id", None, 1), "Program")
        if db.scalar(select(Intake.id).where(Intake.code.ilike(code))):
            raise AgentActionError("That Intake Code now exists.")
        item = Intake(name=name, code=code, start_date=start_date, program_id=program.id)
        db.add(item); db.flush()
        log_audit(db, actor.id, "intake.created", "intake", item.id, None, {"name": item.name, "code": item.code, "source": "ai_agent"})
        return {"entity": "intake", "id": item.id, "name": item.name, "code": item.code}
    if action_type == "create_section":
        name, batch = _string(payload, "name", 50), _get(db, Batch, _integer(payload, "batch_id", None, 1), "Batch")
        if db.scalar(select(Section.id).where(Section.name.ilike(name), Section.batch_id == batch.id)):
            raise AgentActionError("That Section now exists in this Batch.")
        item = Section(name=name, batch_id=batch.id, combined_with=_optional_string(payload, "combined_with", 100))
        db.add(item); db.flush()
        inherited = synchronize_section_module_offerings(db, item)
        log_audit(db, actor.id, "section.created", "section", item.id, None, {"name": item.name, "batch_id": item.batch_id, "inherited_module_offering_ids": [x.id for x in inherited], "source": "ai_agent"})
        return {"entity": "section", "id": item.id, "name": item.name, "batch_id": item.batch_id}
    if action_type == "create_cohort_semester":
        level = _get(db, BatchLevel, _integer(payload, "batch_level_id", None, 1), "Batch Level")
        intake, batch = level.intake, level.batch
        semester, attempt = _integer(payload, "semester_number", None, 1), _integer(payload, "attempt_number", 1, 1)
        start_date, end_date = _date(payload, "start_date"), _date(payload, "end_date")
        status = _optional_string(payload, "status", 20) or "planned"
        if semester not in {level.level_number * 2 - 1, level.level_number * 2}:
            raise AgentActionError(f'Level {level.level_number} does not contain Semester {semester}.')
        if start_date > end_date:
            raise AgentActionError("The cohort semester end date must be on or after its start date.")
        if status not in {"planned", "active", "completed"}:
            raise AgentActionError("Cohort semester status must be planned, active, or completed.")
        if db.scalar(select(CohortSemester.id).where(CohortSemester.intake_id == intake.id, CohortSemester.batch_id == batch.id, CohortSemester.semester_number == semester, CohortSemester.attempt_number == attempt)):
            raise AgentActionError("That dated cohort semester now exists.")
        item = CohortSemester(batch_level_id=level.id, intake_id=intake.id, batch_id=batch.id, semester_number=semester, attempt_number=attempt, start_date=start_date, end_date=end_date, status=status)
        db.add(item); db.flush()
        log_audit(db, actor.id, "cohort_semester.created", "cohort_semester", item.id, None, {**_cohort_data(item), "source": "ai_agent"})
        return {"entity": "cohort_semester", **_cohort_data(item)}
    if action_type == "apply_promotion":
        try:
            run, students = apply_promotion(
                db, intake_id=_integer(payload, "intake_id", None, 1), batch_id=_integer(payload, "batch_id", None, 1),
                from_cohort_semester_id=_integer(payload, "from_cohort_semester_id", None, 1), to_cohort_semester_id=_integer(payload, "to_cohort_semester_id", None, 1),
                effective_date=_date(payload, "effective_date"), section_mapping=_section_mapping(payload.get("section_mapping") or {}),
                hold_student_ids=set(_integer_list(payload.get("hold_student_ids") or [])), preview_signature=_string(payload, "preview_signature", 128), created_by=actor.id, notes=_optional_string(payload, "notes", 500),
            )
        except PromotionValidationError as exc:
            raise AgentActionError(str(exc)) from exc
        promoted, held = sum(x.action == "promote" for x in students), sum(x.action == "hold" for x in students)
        log_audit(db, actor.id, "promotion.applied", "promotion_run", run.id, None, {"source": "ai_agent", "promoted_students": promoted, "held_students": held})
        return {"entity": "promotion_run", "id": run.id, "promoted_students": promoted, "held_students": held}
    raise AgentActionError("The approved action type is not supported.")


def _get(db: Session, model: type[Any], item_id: int | None, label: str) -> Any:
    item = db.get(model, item_id) if item_id else None
    if item is None:
        raise AgentActionError(f"{label} not found.")
    return item


def _string(values: dict[str, Any], key: str, max_length: int) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentActionError(f"{key} is required.")
    value = value.strip()
    if len(value) > max_length:
        raise AgentActionError(f"{key} must be at most {max_length} characters.")
    return value


def _optional_string(values: dict[str, Any], key: str, max_length: int) -> str | None:
    return None if values.get(key) is None else _string(values, key, max_length)


def _integer(values: dict[str, Any], key: str, default: int | None = None, minimum: int | None = None, maximum: int | None = None) -> int:
    value = values.get(key, default)
    if isinstance(value, bool):
        value = None
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        value = int(value)
    if not isinstance(value, int):
        raise AgentActionError(f"{key} must be an integer.")
    if minimum is not None and value < minimum:
        raise AgentActionError(f"{key} must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise AgentActionError(f"{key} must be at most {maximum}.")
    return value


def _optional_integer(values: dict[str, Any], key: str) -> int | None:
    return None if values.get(key) is None else _integer(values, key, None, 1)


def _integer_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        raise AgentActionError("hold_student_ids must be a list of student IDs.")
    return sorted({_integer({"id": x}, "id", None, 1) for x in value})


def _section_mapping(value: Any) -> dict[int, int]:
    if not isinstance(value, dict):
        raise AgentActionError("section_mapping must map source section IDs to target section IDs.")
    return {_integer({"source": source}, "source", None, 1): _integer({"target": target}, "target", None, 1) for source, target in value.items()}


def _date(values: dict[str, Any], key: str) -> date:
    value = values.get(key)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise AgentActionError(f"{key} must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AgentActionError(f"{key} must use YYYY-MM-DD.") from exc


def _student_name(student: Student) -> str:
    return student.user.name if student.user else student.name or student.roll_number


def _three_year_end(start: date) -> date:
    try:
        return start.replace(year=start.year + 3) - timedelta(days=1)
    except ValueError:
        return start.replace(year=start.year + 3, day=28) - timedelta(days=1)


def _cohort_data(item: CohortSemester) -> dict[str, Any]:
    return {"id": item.id, "batch_level_id": item.batch_level_id, "intake_id": item.intake_id, "batch_id": item.batch_id, "semester_number": item.semester_number, "attempt_number": item.attempt_number, "start_date": item.start_date.isoformat(), "end_date": item.end_date.isoformat(), "status": item.status}


def _database_catalog(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    return ToolOutcome(data_catalog(db, actor))


def _database_records(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    try:
        return ToolOutcome(database_records(
            db, actor, _string(args, "dataset", 100), _optional_string(args, "query", 150),
            _integer(args, "limit", 20, 1, 50),
        ))
    except ValueError as exc:
        raise AgentActionError(str(exc)) from exc


def _import_history(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    try:
        return ToolOutcome(import_history(
            db, _optional_integer(args, "import_job_id"), _integer(args, "limit", 20, 1, 50),
        ))
    except ValueError as exc:
        raise AgentActionError(str(exc)) from exc


def _google_form_responses(db: Session, actor: User, args: dict[str, Any]) -> ToolOutcome:
    try:
        return ToolOutcome(google_form_responses(
            _integer(args, "limit", settings.google_forms_response_limit, 1, 100),
        ))
    except ValueError as exc:
        raise AgentActionError(str(exc)) from exc
