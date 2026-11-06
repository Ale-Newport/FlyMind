"""Process-wide service state: session managers and the background job runner."""

from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from flymind.brain.session import SessionManager
from flymind.common.provenance import utc_now
from flymind.embodiment.session import FlySessionManager


@dataclass
class Job:
    id: str
    kind: str
    label: str
    status: str = "queued"  # queued | running | done | failed | cancelled
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict:
        return {
            k: getattr(self, k)
            for k in (
                "id",
                "kind",
                "label",
                "status",
                "progress",
                "message",
                "result",
                "error",
                "created_at",
                "finished_at",
            )
        }


class JobRunner:
    def __init__(self, workers: int = 2):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self.jobs: dict[str, Job] = {}

    def submit(self, kind: str, label: str, fn: Callable[[Job], Any]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, label=label)
        self.jobs[job.id] = job

        def run():
            if job.cancel.is_set():
                job.status = "cancelled"
                return
            job.status = "running"
            try:
                job.result = fn(job)
                job.status = "cancelled" if job.cancel.is_set() else "done"
                job.progress = 1.0 if job.status == "done" else job.progress
            except Exception as exc:  # reported through the job API
                from flymind.experiments.runner import Cancelled

                if isinstance(exc, Cancelled):
                    job.status = "cancelled"
                else:
                    job.status = "failed"
                    job.error = f"{type(exc).__name__}: {exc}"
                    job.message = traceback.format_exc(limit=3)
            finally:
                job.finished_at = utc_now()

        self.pool.submit(run)
        return job

    def get(self, job_id: str) -> Job:
        if job_id not in self.jobs:
            raise KeyError(f"no job {job_id}")
        return self.jobs[job_id]

    def shutdown(self) -> None:
        for j in self.jobs.values():
            j.cancel.set()
        self.pool.shutdown(wait=False, cancel_futures=True)


class ServiceState:
    def __init__(self) -> None:
        self.sims = SessionManager(max_sessions=6)
        self.flies = FlySessionManager(max_sessions=3)
        self.jobs = JobRunner(workers=2)

    def shutdown(self) -> None:
        self.sims.shutdown()
        self.flies.shutdown()
        self.jobs.shutdown()
