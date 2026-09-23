import json

import pytest
from sqlalchemy import select

from app.modules.agent import read_tools
from app.modules.agent.tools import AgentActionError, execute_tool
from app.modules.identity.models import User
from app.modules.operations.models import ImportJob
from test_canonical_conflicts_effective import setup_context


@pytest.fixture
def context():
    factory, ids = setup_context()
    try:
        with factory() as db:
            actor = db.scalar(select(User).where(User.email == "admin@example.com"))
            yield db, actor, ids
    finally:
        pass


def test_database_catalog_and_records_are_bounded_and_redacted(context):
    db, actor, _ = context
    catalog = execute_tool(db, actor, "get_database_catalog", {}).data
    datasets = {entry["dataset"]: entry for entry in catalog["datasets"]}
    assert "blocks" in datasets
    assert "users" in datasets
    assert "agent_approvals" not in datasets
    assert "email" not in datasets["users"]["columns"]

    records = execute_tool(db, actor, "read_database_records", {"dataset": "blocks", "limit": 5}).data
    assert records["dataset"] == "blocks"
    assert records["returned_count"] >= 1
    assert {"id", "name"}.issubset(records["columns"])

    with pytest.raises(AgentActionError, match="not available"):
        execute_tool(db, actor, "read_database_records", {"dataset": "agent_approvals"})


def test_import_history_redacts_contact_data(context):
    db, actor, _ = context
    job = ImportJob(
        uploaded_by=actor.id,
        file_name="students.xlsx",
        upload_type="students",
        total_rows=1,
        success_count=1,
        failed_count=0,
        results_json=json.dumps([{
            "row_number": 2,
            "status": "success",
            "message": "Imported learner@example.com",
            "data": {"name": "Learner", "email": "learner@example.com", "phone": "+977 9800000000"},
        }]),
    )
    db.add(job)
    db.flush()

    result = execute_tool(db, actor, "get_import_history", {"import_job_id": job.id}).data
    row = result["rows"][0]
    assert row["message"] == "Imported [redacted email]"
    assert row["data"]["email"] == "[redacted]"
    assert row["data"]["phone"] == "[redacted]"
    assert row["data"]["name"] == "Learner"


def test_google_forms_reader_uses_read_only_data_and_redacts_sensitive_answers(context, monkeypatch):
    db, actor, _ = context
    monkeypatch.setattr(read_tools.settings, "google_forms_enabled", True)
    monkeypatch.setattr(read_tools.settings, "google_forms_form_id", "form-123")
    monkeypatch.setattr(read_tools.settings, "google_forms_access_token", "test-token")

    class Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        if url.endswith("/responses"):
            return Response({"responses": [{
                "responseId": "response-1",
                "lastSubmittedTime": "2026-09-24T10:00:00Z",
                "respondentEmail": "hidden@example.com",
                "answers": {
                    "question-name": {"textAnswers": {"answers": [{"value": "Ada"}]}},
                    "question-email": {"textAnswers": {"answers": [{"value": "ada@example.com"}]}},
                },
            }]})
        return Response({"items": [
            {"title": "Student name", "questionItem": {"question": {"questionId": "question-name"}}},
            {"title": "Email address", "questionItem": {"question": {"questionId": "question-email"}}},
        ]})

    monkeypatch.setattr(read_tools.httpx, "get", fake_get)
    result = execute_tool(db, actor, "get_google_form_responses", {"limit": 5}).data
    answers = result["responses"][0]["answers"]
    assert answers["Student name"] == ["Ada"]
    assert answers["Email address"] == ["[redacted]"]
    assert "respondentEmail" not in str(result)
    assert result["untrusted_source_data"] is True
