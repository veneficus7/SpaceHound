"""Background jobs with progress reporting and cooperative cancellation."""

import itertools
import threading
import time
import traceback


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, job_id, kind):
        self.id = job_id
        self.kind = kind
        self.state = "running"
        self.progress = {}
        self.result = None
        self.error = None
        self.started = time.time()
        self.finished = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    # called from the worker ---------------------------------------------
    def update(self, **values):
        with self._lock:
            self.progress.update(values)

    def check(self):
        if self._cancel.is_set():
            raise Cancelled()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    # called from the UI ---------------------------------------------------
    def cancel(self):
        self._cancel.set()

    def status(self, include_result=True):
        with self._lock:
            out = {
                "id": self.id,
                "kind": self.kind,
                "state": self.state,
                "progress": dict(self.progress),
                "elapsed": (self.finished or time.time()) - self.started,
                "error": self.error,
            }
        if include_result and self.state == "done":
            out["result"] = self.result
        return out


class JobManager:
    def __init__(self):
        self._jobs = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def start(self, kind, fn, *args, **kwargs):
        job = Job(next(self._ids), kind)
        with self._lock:
            self._jobs[job.id] = job
            # keep memory bounded: forget old finished jobs
            done = [j for j in self._jobs.values() if j.state != "running"]
            for old in done[:-20]:
                self._jobs.pop(old.id, None)

        def run():
            try:
                job.result = fn(job, *args, **kwargs)
                job.state = "done"
            except Cancelled:
                job.state = "cancelled"
            except Exception as exc:  # surface to the UI instead of dying silently
                job.error = f"{type(exc).__name__}: {exc}"
                job.state = "error"
                traceback.print_exc()
            finally:
                job.finished = time.time()

        threading.Thread(target=run, name=f"job-{kind}-{job.id}", daemon=True).start()
        return job

    def get(self, job_id):
        return self._jobs.get(int(job_id))

    def running(self, kind=None):
        return [j for j in self._jobs.values() if j.state == "running" and (kind is None or j.kind == kind)]

    def cancel_all(self):
        for j in list(self._jobs.values()):
            j.cancel()
