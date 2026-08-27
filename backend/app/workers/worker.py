from queue import Empty
from time import sleep

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.operations.models import Notification, NotificationStatus
from app.workers.jobs.notification_job import handle as handle_notification
from app.workers.queue_client import job_queue


def process_pending_notifications(limit: int | None = None) -> int:
    """Drain durable pending-email records, even after a process restart."""

    batch_size = limit or settings.notification_worker_batch_size
    with SessionLocal() as db:
        ids = list(
            db.scalars(
                select(Notification.id)
                .where(Notification.status == NotificationStatus.PENDING)
                .order_by(Notification.created_at, Notification.id)
                .limit(batch_size)
            )
        )
    return sum(handle_notification({"notification_id": notification_id}) for notification_id in ids)


def dispatch(job: dict) -> None:
    job_type = job.get("type")
    if job_type == "notification":
        handle_notification(job)
    else:
        print(f"Unknown worker job type: {job_type or 'unknown'}")


def run() -> None:
    print("Notification worker started")
    while True:
        processed = process_pending_notifications()
        if processed:
            continue
        try:
            dispatch(job_queue.get(timeout=settings.notification_worker_poll_seconds))
            job_queue.task_done()
        except Empty:
            sleep(0)


if __name__ == "__main__":
    run()
