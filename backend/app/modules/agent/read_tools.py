"""Bounded, read-only sources available to the administrative AI assistant."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from enum import Enum
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import String, Text, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Base
from app.modules.identity.models import User
from app.modules.operations.models import ImportJob
from app.modules.google_workspace import service as google_workspace_service

# Import every model package so the metadata catalog is complete when this
# module is used outside the normal FastAPI startup path (for example, tests).
from app.modules.academic import models as academic_models  # noqa: F401
from app.modules.attendance import models as attendance_models  # noqa: F401
from app.modules.course_completion import models as course_completion_models  # noqa: F401
from app.modules.crm import models as crm_models  # noqa: F401
from app.modules.operations import models as operations_models  # noqa: F401
from app.modules.scheduling import models as scheduling_models  # noqa: F401


_BLOCKED_TABLES = frozenset({
    "alembic_version", "agent_approvals", "attendance_challenges",
    "auth_rate_limits", "pending_attendance_verifications",
})
_PRIVATE_COLUMNS = frozenset({
    "address", "avatar_content_type", "avatar_data", "avatar_key", "body",
    "client_ip", "code_ciphertext", "code_hash", "confirm_client_ip",
    "details", "email", "errors_json", "failure_reason", "html_body",
    "ip_status", "is_locked", "last_failed_login_at", "latitude", "locked_at", "longitude", "notes", "outcome",
    "password_hash", "payload_json", "phone", "preview_json", "qr_nonce",
    "reason", "reset_expires_at", "reset_requested_at", "reset_token_hash",
    "results_json", "session_version", "token_hash",
})
_PRIVATE_PARTS = ("password", "secret", "token", "hash", "cipher", "avatar", "geofence")
_SENSITIVE_LABELS = ("address", "email", "phone", "mobile", "password", "location", "latitude", "longitude", "name", "full name", "student name", "respondent name", "student id", "respondent id", "roll number", "roll no", "registration number", "student number")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.+-])")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .-]{7,}\d)(?!\w)")


def _private_column(name: str) -> bool:
    folded = name.casefold()
    return folded in _PRIVATE_COLUMNS or any(part in folded for part in _PRIVATE_PARTS)


def _visible_tables() -> dict[str, Any]:
    return {
        name: table for name, table in Base.metadata.tables.items()
        if name not in _BLOCKED_TABLES and any(not _private_column(column.name) for column in table.columns)
    }


def _safe_columns(table: Any) -> list[Any]:
    return [column for column in table.columns if not _private_column(column.name)]


def _scope_filters(db: Session, actor: User, table: Any) -> list[Any]:
    if "college_id" not in table.c:
        return []
    scope = db.info.get("college_id")
    if scope is None and actor.role.value != "super_admin":
        scope = actor.college_id
    return [table.c.college_id == scope] if scope is not None else []


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def data_catalog(db: Session, actor: User) -> dict[str, Any]:
    datasets = []
    for name, table in sorted(_visible_tables().items()):
        filters = _scope_filters(db, actor, table)
        count = db.scalar(select(func.count()).select_from(table).where(*filters)) or 0
        datasets.append({
            "dataset": name,
            "columns": [column.name for column in _safe_columns(table)],
            "row_count": count,
        })
    return {
        "datasets": datasets,
        "note": "Only the active college is included. Authentication, contact, location, token, and free-text private fields are excluded.",
    }


def database_records(db: Session, actor: User, dataset: str, query: str | None, limit: int) -> dict[str, Any]:
    table = _visible_tables().get(dataset)
    if table is None:
        raise ValueError("That dataset is not available for AI read access. Call get_data_catalog first.")
    columns = _safe_columns(table)
    filters = _scope_filters(db, actor, table)
    if query:
        text_columns = [column for column in columns if isinstance(column.type, (String, Text))]
        if not text_columns:
            raise ValueError("That dataset has no searchable safe text fields.")
        pattern = f"%{query.strip()}%"
        filters.append(or_(*(column.ilike(pattern) for column in text_columns)))
    total = db.scalar(select(func.count()).select_from(table).where(*filters)) or 0
    statement = select(*columns).select_from(table).where(*filters)
    if "id" in table.c:
        statement = statement.order_by(table.c.id.desc())
    rows = [
        {key: _json_value(value) for key, value in row._mapping.items()}
        for row in db.execute(statement.limit(limit)).all()
    ]
    return {
        "dataset": dataset,
        "matching_count": total,
        "returned_count": len(rows),
        "columns": [column.name for column in columns],
        "records": rows,
    }


def _redact_text(value: str) -> str:
    return _PHONE.sub("[redacted phone]", _EMAIL.sub("[redacted email]", value))


def _safe_import_value(key: str, value: Any) -> Any:
    if _private_column(key):
        return "[redacted]"
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {str(item_key): _safe_import_value(str(item_key), item_value) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_safe_import_value(key, item) for item in value]
    return _json_value(value)


def import_history(db: Session, import_job_id: int | None, limit: int) -> dict[str, Any]:
    if import_job_id is None:
        jobs = db.scalars(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(limit)).all()
        return {"jobs": [_import_job_summary(job) for job in jobs], "note": "Original spreadsheets are not retained. Only saved import outcomes are available."}
    job = db.get(ImportJob, import_job_id)
    if job is None:
        raise ValueError("Import job not found.")
    try:
        stored_rows = json.loads(job.results_json or "[]")
    except json.JSONDecodeError:
        stored_rows = []
    rows = []
    for item in stored_rows[:limit]:
        rows.append({
            "row_number": item.get("row_number"),
            "status": item.get("status"),
            "message": _redact_text(str(item.get("message", ""))),
            "data": _safe_import_value("data", item.get("data") or {}),
        })
    return {"job": _import_job_summary(job), "rows": rows, "returned_count": len(rows)}


def _import_job_summary(job: ImportJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "file_name": job.file_name,
        "upload_type": job.upload_type,
        "total_rows": job.total_rows,
        "success_count": job.success_count,
        "failed_count": job.failed_count,
        "pending_section_references": job.pending_section_references,
        "created_at": _json_value(job.created_at),
    }


class _GoogleFormsError(ValueError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _google_request(url: str, headers: dict[str, str], params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        response = httpx.get(url, headers=headers, params=params, timeout=settings.google_forms_timeout_seconds)
    except httpx.HTTPError as exc:
        raise _GoogleFormsError("Google Forms is temporarily unavailable.") from exc
    if response.status_code in {401, 403}:
        raise _GoogleFormsError("Google Forms authorization failed. Check the read-only token scopes and form sharing.", response.status_code)
    if response.status_code >= 400:
        raise _GoogleFormsError("Google Forms could not return responses right now.", response.status_code)
    return response.json()


def _question_titles(items: list[dict[str, Any]]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for item in items:
        title = str(item.get("title") or "Untitled question")
        question = (item.get("questionItem") or {}).get("question") or {}
        if question.get("questionId"):
            titles[str(question["questionId"])] = title
        for grouped_question in ((item.get("questionGroupItem") or {}).get("questions") or []):
            if grouped_question.get("questionId"):
                titles[str(grouped_question["questionId"])] = title
        titles.update(_question_titles(item.get("items") or []))
    return titles


def _answer_values(answer: dict[str, Any]) -> list[str]:
    text_answers = ((answer.get("textAnswers") or {}).get("answers") or [])
    if text_answers:
        return [str(item.get("value", "")) for item in text_answers]
    uploads = ((answer.get("fileUploadAnswers") or {}).get("answers") or [])
    return [f"Uploaded file: {item.get('fileName', 'unnamed file')}" for item in uploads]



def _google_access_token() -> str:
    if settings.google_forms_access_token:
        return settings.google_forms_access_token
    client_id = settings.google_forms_oauth_client_id
    client_secret = settings.google_forms_oauth_client_secret
    refresh_token = settings.google_forms_oauth_refresh_token
    if not client_id or not client_secret or not refresh_token:
        raise ValueError(
            "Google Forms is not configured. Set GOOGLE_FORMS_ACCESS_TOKEN, or configure the OAuth client ID, secret, and refresh token on the server."
        )
    try:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=settings.google_forms_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise ValueError("Google OAuth is temporarily unavailable.") from exc
    if response.status_code >= 400:
        raise ValueError("Google OAuth could not refresh the read-only Forms token. Reauthorize the Google connection.")
    try:
        token = str(response.json().get("access_token") or "")
    except ValueError as exc:
        raise ValueError("Google OAuth returned an invalid token response.") from exc
    if not token:
        raise ValueError("Google OAuth did not return an access token.")
    return token


def google_form_responses(limit: int) -> dict[str, Any]:
    if not settings.google_forms_enabled:
        raise ValueError("Google Forms access is disabled. Set GOOGLE_FORMS_ENABLED=true after configuring a read-only token.")
    if not settings.google_forms_form_id:
        raise ValueError("Google Forms is not configured. Set GOOGLE_FORMS_FORM_ID on the server.")
    form_id = settings.google_forms_form_id
    headers = {"Authorization": f"Bearer {_google_access_token()}"}
    base_url = f"https://forms.googleapis.com/v1/forms/{quote(form_id, safe='')}"
    response_data = _google_request(f"{base_url}/responses", headers, {"pageSize": limit})
    question_titles: dict[str, str] = {}
    form_title = None
    metadata_warning = None
    try:
        form_definition = _google_request(base_url, headers)
        question_titles = _question_titles(form_definition.get("items") or [])
        form_title = (form_definition.get("info") or {}).get("title")
    except _GoogleFormsError as exc:
        if exc.status_code in {401, 403}:
            metadata_warning = "Question titles are unavailable because forms.body.readonly was not granted; question IDs are shown instead."
        else:
            raise
    responses = []
    for response in response_data.get("responses") or []:
        answers = {}
        for question_id, answer in (response.get("answers") or {}).items():
            label = question_titles.get(question_id, f"Question {question_id}")
            values = _answer_values(answer)
            answers[label] = ["[redacted]" if _sensitive_feedback_label(label) else _redact_text(value) for value in values]
        responses.append({
            "response_id": response.get("responseId"),
            "submitted_at": response.get("lastSubmittedTime") or response.get("createTime"),
            "answers": answers,
        })
    return {
        "form_id": form_id,
        "form_title": form_title,
        "returned_count": len(responses),
        "next_page_available": bool(response_data.get("nextPageToken")),
        "responses": responses,
        "metadata_warning": metadata_warning,
        "untrusted_source_data": True,
    }


def google_workspace_files(
    db: Session,
    *,
    query: str | None = None,
    file_type: str = "all",
    limit: int = 25,
) -> dict[str, Any]:
    try:
        connection = google_workspace_service.get_connection(db)
        result = google_workspace_service.list_drive_files(
            connection,
            query=query,
            file_type=file_type,
            page_size=min(max(limit, 1), 50),
        )
    except google_workspace_service.GoogleWorkspaceError as exc:
        raise ValueError(exc.detail) from exc
    files = []
    for item in result.get("files") or []:
        mime_type = str(item.get("mimeType") or "")
        if mime_type == "application/vnd.google-apps.form":
            kind = "form"
        elif mime_type == "application/vnd.google-apps.spreadsheet":
            kind = "spreadsheet"
        else:
            continue
        files.append({
            "file_id": str(item.get("id") or ""),
            "title": str(item.get("name") or "Untitled file"),
            "type": kind,
            "modified_time": item.get("modifiedTime"),
        })
    return {
        "files": files,
        "next_page_available": bool(result.get("nextPageToken")),
        "untrusted_source_data": True,
    }


def _sensitive_feedback_label(label: str) -> bool:
    folded = label.casefold()
    if "teacher" in folded and "name" in folded and "student" not in folded and "respondent" not in folded:
        return False
    return any(sensitive in folded for sensitive in _SENSITIVE_LABELS)


def _safe_feedback_value(value: Any) -> Any:
    return _redact_text(value) if isinstance(value, str) else value


def _spreadsheet_column_number(label: str) -> int:
    total = 0
    for character in label.upper():
        total = total * 26 + ord(character) - ord("A") + 1
    return total


def _bounded_feedback_range(cell_range: str, *, max_rows: int) -> str:
    value = cell_range.strip()
    notation = value.rsplit("!", 1)[-1]
    match = re.fullmatch(r"\$?([A-Za-z]+)\$?(\d+):\$?([A-Za-z]+)\$?(\d+)", notation)
    if not match:
        raise ValueError("Use a bounded A1 range such as 'Form Responses 1'!A1:Z51.")
    start_column, start_row, end_column, end_row = match.groups()
    start_row, end_row = int(start_row), int(end_row)
    if (
        start_row < 1 or end_row < start_row or end_row - start_row + 1 > max_rows
        or _spreadsheet_column_number(end_column) > 52
        or _spreadsheet_column_number(end_column) < _spreadsheet_column_number(start_column)
    ):
        raise ValueError(f"Google Sheet reads are limited to {max_rows} rows and 52 columns.")
    return value


def _safe_feedback_rows(values: list[list[Any]]) -> list[list[Any]]:
    if not values:
        return []
    private_columns = {
        index for index, value in enumerate(values[0])
        if _sensitive_feedback_label(str(value or ""))
    }
    result: list[list[Any]] = []
    for row_index, row in enumerate(values):
        cleaned = []
        for column_index, value in enumerate(row):
            if column_index in private_columns:
                cleaned.append("[private field]" if row_index == 0 else "[redacted]")
            else:
                cleaned.append(_safe_feedback_value(value))
        result.append(cleaned)
    return result


def _form_questions_for_ai(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    questions = []
    for item in items:
        question = ((item.get("questionItem") or {}).get("question") or {})
        if question:
            question_type = next(
                (key for key in ("choiceQuestion", "scaleQuestion", "textQuestion", "dateQuestion") if key in question),
                "question",
            )
            options = ((question.get("choiceQuestion") or {}).get("options") or [])
            questions.append({
                "title": str(item.get("title") or "Untitled question"),
                "type": question_type,
                "required": bool(question.get("required")),
                "options": [str(option.get("value") or "") for option in options],
            })
        questions.extend(_form_questions_for_ai(item.get("items") or []))
    return questions


def google_workspace_file_content(
    db: Session,
    *,
    file_id: str,
    limit: int = 50,
    cell_range: str | None = None,
) -> dict[str, Any]:
    try:
        connection = google_workspace_service.get_connection(db)
        file = google_workspace_service.drive_file_metadata(connection, file_id)
        mime_type = str(file.get("mimeType") or "")
        if mime_type == "application/vnd.google-apps.form":
            form = google_workspace_service.form_definition(connection, file_id)
            data = google_workspace_service.form_responses_for_file(
                connection, file_id, page_size=min(max(limit, 1), 100),
            )
            titles = data.get("questionTitles") or {}
            responses = []
            for response in data.get("responses") or []:
                answers = {}
                for question_id, answer in (response.get("answers") or {}).items():
                    title = str(titles.get(question_id) or f"Question {question_id}")
                    text_values = (((answer.get("textAnswers") or {}).get("answers")) or [])
                    values = [str(item.get("value") or "") for item in text_values]
                    if not values and (answer.get("fileUploadAnswers") or {}).get("answers"):
                        values = ["[file response omitted]"]
                    answers[title] = (
                        ["[redacted]"] if _sensitive_feedback_label(title)
                        else [_redact_text(value) for value in values]
                    )
                responses.append({
                    "submitted_at": response.get("lastSubmittedTime") or response.get("createTime"),
                    "answers": answers,
                })
            return {
                "file_id": file_id,
                "title": str((form.get("info") or {}).get("title") or file.get("name") or "Google Form"),
                "type": "form",
                "questions": _form_questions_for_ai(form.get("items") or []),
                "returned_count": len(responses),
                "next_page_available": bool(data.get("nextPageToken")),
                "responses": responses,
                "untrusted_source_data": True,
                "privacy_note": "Respondent emails and answers to sensitive identity/contact fields are excluded or redacted.",
            }
        if mime_type == "application/vnd.google-apps.spreadsheet":
            sheet = google_workspace_service.spreadsheet_metadata(connection, file_id)
            tabs = sheet.get("sheets") or []
            first_title = str(((tabs[0].get("properties") or {}).get("title")) if tabs else "Sheet1")
            if not cell_range:
                escaped_title = first_title.replace("'", "''")
                cell_range = f"'{escaped_title}'!A1:Z{min(max(limit, 1) + 1, 101)}"
            safe_range = _bounded_feedback_range(cell_range, max_rows=min(max(limit, 1) + 1, 101))
            values = google_workspace_service.read_spreadsheet_values(connection, file_id, safe_range)
            return {
                "file_id": file_id,
                "title": str((sheet.get("properties") or {}).get("title") or file.get("name") or "Google Sheet"),
                "type": "spreadsheet",
                "range": values.get("range"),
                "returned_rows": len(values.get("values") or []),
                "values": _safe_feedback_rows(values.get("values") or []),
                "untrusted_source_data": True,
                "privacy_note": "Values under student identity/contact columns and email/phone-like text are redacted.",
            }
        raise ValueError("Choose a Google Form or Google Sheet to read feedback data.")
    except google_workspace_service.GoogleWorkspaceError as exc:
        raise ValueError(exc.detail) from exc
