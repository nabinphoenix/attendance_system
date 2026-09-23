"""College ownership and request-scoped ORM enforcement.

HTTP sessions start closed. Authentication selects the scope from the stored
account; only a super admin may select a different college. Trusted CLI/worker
sessions may operate globally, but still validate ownership on writes.
"""
from sqlalchemy import ForeignKey, Integer, event, inspect, select
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria
from fastapi import HTTPException


def ownership_default(context):
    # SQLAlchemy emits secondary relationship inserts without mapped objects.
    # Derive their owner from a referenced row, never from a browser header.
    params = context.get_current_parameters()
    table = context.compiled.statement.table
    for fk in table.foreign_keys:
        if fk.parent.name == "college_id" or fk.column.table.name == "users":
            continue
        value = params.get(fk.parent.name)
        if value is not None and "college_id" in fk.column.table.c:
            return context.connection.scalar(select(fk.column.table.c.college_id).where(fk.column == value))
    return 1  # legacy seed/test data belongs to Techspire


class CollegeOwned:
    college_id: Mapped[int] = mapped_column(
        ForeignKey("colleges.id"), nullable=False, index=True, default=ownership_default
    )


def set_college_scope(db: Session, college_id: int | None):
    db.info["college_id"] = college_id


@event.listens_for(Session, "do_orm_execute")
def restrict_college_queries(state):
    scope = state.session.info.get("college_id")
    if scope is None or state.execution_options.get("tenant_bypass"):
        return
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(CollegeOwned, lambda model: model.college_id == scope, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def protect_college_writes(db, flush_context, instances):
    scope = db.info.get("college_id")
    objects = list(db.new) + list(db.dirty) + list(db.deleted)
    for obj in objects:
        if not isinstance(obj, CollegeOwned):
            continue
        state = inspect(obj)
        is_platform_user = getattr(getattr(obj, "role", None), "value", None) == "super_admin"
        is_global_audit = obj.__tablename__ == "audit_logs" and scope is None
        if obj in db.new and obj.college_id is None and not is_platform_user and not is_global_audit:
            obj.college_id = scope if scope is not None else 1
        if scope is not None and obj.college_id != scope:
            # A super admin's own profile remains global in a college workspace.
            if not (is_platform_user and obj.id == db.info.get("actor_id") and obj not in db.deleted):
                raise HTTPException(403, "This record belongs to another college")
        if obj not in db.new and state.attrs.college_id.history.has_changes():
            raise HTTPException(422, "Existing records cannot be moved between colleges")
        if is_platform_user and obj.college_id is not None:
            raise HTTPException(422, "Super admins cannot belong to a college")
        for fk in state.mapper.local_table.foreign_keys:
            if fk.parent.name == "college_id" or "college_id" not in fk.column.table.c:
                continue
            value = getattr(obj, fk.parent.name)
            if value is None:
                continue
            row = db.connection().execute(select(fk.column.table.c.college_id).where(fk.column == value)).first()
            if row and row[0] != obj.college_id:
                # Global super admins may be audit actors, uploaders, approvers.
                actor_columns = {"actor_id", "uploaded_by", "created_by", "approved_by", "changed_by", "staff_id", "requested_by"}
                if fk.column.table.name == "users" and row[0] is None and fk.parent.name in actor_columns:
                    continue
                raise HTTPException(422, "Related records must belong to the same college")
        for relation in state.mapper.relationships:
            for related in state.attrs[relation.key].history.added:
                if isinstance(related, CollegeOwned):
                    if related in db.new and related.college_id is None:
                        related.college_id = obj.college_id
                    if related.college_id != obj.college_id:
                        raise HTTPException(422, "Related records must belong to the same college")


# Capture ordinary CRUD operations as well as the explicit domain audit events.
# Secrets, uploaded binaries, and message bodies are never copied into the log.
_AUDIT_PRIVATE = {"password_hash", "token_hash", "avatar_data", "avatar_key", "pdf_data", "body", "html_body", "payload_json", "preview_json", "details", "errors_json", "results_json"}

@event.listens_for(Session, "before_flush")
def collect_audit_changes(db, flush_context, instances):
    if not db.info.get("actor_id"):
        return
    pending = []
    for obj in list(db.new) + list(db.dirty) + list(db.deleted):
        if not isinstance(obj, CollegeOwned) or obj.__tablename__ == "audit_logs":
            continue
        state = inspect(obj)
        action = "created" if obj in db.new else "deleted" if obj in db.deleted else "updated"
        before, after = {}, {}
        for attr in state.mapper.column_attrs:
            key = attr.key
            if key in _AUDIT_PRIVATE or any(word in key for word in ("password", "secret", "token", "code_hash")):
                continue
            history = state.attrs[key].history
            if action == "created":
                after[key] = getattr(obj, key)
            elif action == "deleted":
                before[key] = getattr(obj, key)
            elif history.has_changes():
                before[key] = history.deleted[0] if history.deleted else None
                after[key] = getattr(obj, key)
        if action == "updated" and not after:
            continue
        pending.append((obj, action, before or None, after or None))
    db.info["audit_pending"] = pending


@event.listens_for(Session, "after_flush_postexec")
def write_audit_changes(db, flush_context):
    import json
    from app.modules.operations.models import AuditLog
    for obj, action, before, after in db.info.pop("audit_pending", []):
        db.add(AuditLog(actor_id=db.info["actor_id"], college_id=obj.college_id,
            action=f"record.{action}", entity_type=obj.__tablename__, entity_id=obj.id,
            details=json.dumps({"before": before, "after": after}, default=str)))
