from app.workers.queue_client import job_queue
def run() -> None:
    while True:
        job = job_queue.get()
        print(f"Received job: {job.get('type', 'unknown')}")
        job_queue.task_done()
if __name__ == "__main__": run()
