"""Small concurrency helpers for worker-thread sessions."""

from __future__ import annotations

import threading
import time


class YieldingLock:
    """Re-entrant lock that lets a busy worker loop yield to waiting requesters.

    ``threading.RLock`` is not fair: a worker that releases and immediately
    re-acquires the lock between simulation chunks can starve API requests
    (pause/stop/add stimulus) for seconds. Requesters register as waiters, and the
    worker calls :meth:`yield_to_waiters` after each chunk.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._count_lock = threading.Lock()
        self.waiting = 0

    def __enter__(self) -> YieldingLock:
        with self._count_lock:
            self.waiting += 1
        self._lock.acquire()
        with self._count_lock:
            self.waiting -= 1
        return self

    def __exit__(self, *exc) -> None:
        self._lock.release()

    def yield_to_waiters(self, timeout: float = 0.5) -> None:
        deadline = time.perf_counter() + timeout
        while self.waiting > 0 and time.perf_counter() < deadline:
            time.sleep(0.0005)
