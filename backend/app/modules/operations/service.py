import json
from sqlalchemy.orm import Session
from app.modules.operations.models import AuditLog,Notification
def log_audit(db: Session, actor_id: int, action: str, entity_type: str, entity_id: int, before=None, after=None, college_id: int | None = None) -> AuditLog:
    obj = AuditLog(actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id, details=json.dumps({"before": before, "after": after}, default=str), college_id=college_id)
    db.add(obj)
    return obj


def queue_notification(db: Session, recipient_type: str, recipient_id: int, subject: str, body: str, related_entity: str | None = None, related_entity_id: int | None = None, channel: str = "email", html_body: str | None = None, actor_id: int | None = None, college_id: int | None = None) -> Notification:
    obj = Notification(recipient_type=recipient_type, recipient_id=recipient_id, channel=channel, subject=subject, body=body, html_body=html_body, related_entity=related_entity, related_entity_id=related_entity_id, actor_id=actor_id if actor_id is not None else db.info.get("actor_id"), college_id=college_id)
    db.add(obj)
    return obj
