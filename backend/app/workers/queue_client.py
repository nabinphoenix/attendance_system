from queue import Queue
job_queue: Queue[dict] = Queue()
def enqueue(job: dict) -> None: job_queue.put(job)
