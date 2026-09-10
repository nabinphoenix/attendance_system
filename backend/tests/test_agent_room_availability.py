from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.main import app
from app.modules.agent import tools
from app.modules.agent.tools import AgentActionError, execute_tool
from app.modules.identity.models import User
from app.modules.scheduling.models import OverrideStatus, ScheduleOverride
from test_canonical_conflicts_effective import setup_context


@pytest.fixture
def context():
    factory, ids = setup_context()
    try:
        with factory() as db:
            actor = db.scalar(select(User).where(User.email == "admin@example.com"))
            yield db, actor, ids
    finally:
        app.dependency_overrides.clear()


def lookup(context, **args):
    db, actor, _ = context
    return execute_tool(db, actor, "get_room_availability", args)


@pytest.mark.parametrize("at_time,expected", [("07:59", "available"), ("08:00", "occupied"), ("08:59", "occupied"), ("09:00", "available"), ("23:00", "available")])
def test_room_instant_boundaries(context, at_time, expected):
    outcome = lookup(context, block_name=" b ", date=date.today().isoformat(), time=at_time)
    assert outcome.pending is None
    assert len(outcome.data["blocks"]) == 1
    rooms = {r["name"]: r for r in outcome.data["blocks"][0]["rooms"]}
    assert rooms["Annapurna"]["status"] == expected
    assert rooms["Codespace"]["status"] == "available"
    if at_time == "07:59":
        assert rooms["Annapurna"]["next_class_at"] == "08:00:00"


def test_approved_room_move_and_cancellation(context):
    db, actor, ids = context
    override = ScheduleOverride(routine_entry_id=ids["base"], override_date=date.today(), new_room_id=ids["room_Codespace"], reason="Move room", created_by=actor.id, status=OverrideStatus.APPROVED)
    db.add(override)
    db.flush()
    data = lookup(context, block_name="BLOCK B", date=date.today().isoformat(), time="08:30").data
    rooms = {r["name"]: r for r in data["blocks"][0]["rooms"]}
    assert rooms["Annapurna"]["status"] == "available"
    assert rooms["Codespace"]["status"] == "occupied"
    override.is_cancelled = True
    db.flush()
    data = lookup(context, time="08:30", date=date.today().isoformat()).data
    assert all(r["status"] == "available" for b in data["blocks"] for r in b["rooms"])


def test_now_uses_nepal_date_and_time(context, monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(tools, "datetime", FrozenDatetime)
    data = lookup(context, block_name="B").data
    assert data["date"] == "2026-09-06"
    assert data["time"] == "01:45:00"
    assert data["timezone"] == "Asia/Kathmandu"


@pytest.mark.parametrize("args", [{"block_name": "missing"}, {"time": "25:00"}, {"time": "8:00"}, {"date": "invalid"}])
def test_invalid_queries(context, args):
    with pytest.raises(AgentActionError):
        lookup(context, **args)


def test_non_admin_cannot_read(context):
    db, _, _ = context
    actor = db.scalar(select(User).where(User.email == "karan@example.com"))
    with pytest.raises(AgentActionError, match="administrator"):
        execute_tool(db, actor, "get_room_availability", {})


def test_agent_routes_room_tool_result_back_to_provider(context, monkeypatch):
    import json
    from app.modules.agent import graph
    from app.modules.agent.providers import ProviderReply, ToolCall

    class FakeClient:
        def complete(self, messages, definitions):
            assert any(t["function"]["name"] == "get_room_availability" for t in definitions)
            if messages[-1]["role"] == "user":
                assert "avaible" in messages[-1]["content"]
                return ProviderReply("test", "", [ToolCall("rooms", "get_room_availability", {"block_name": "B", "date": date.today().isoformat(), "time": "08:30"})]), []
            assert messages[-1]["role"] == "tool"
            result = json.loads(messages[-1]["content"])
            rooms = {r["name"]: r for r in result["blocks"][0]["rooms"]}
            assert rooms["Codespace"]["status"] == "available"
            return ProviderReply("test", "Codespace is available at 08:30 Nepal time.", []), []

    monkeypatch.setattr(graph, "FallbackModelClient", FakeClient)
    db, actor, _ = context
    result = graph.run_agent(db, actor, "which room is avaible now in block b?")
    assert result["status"] == "completed"
    assert "Codespace" in result["message"]
    assert result["confirmation_token"] is None
