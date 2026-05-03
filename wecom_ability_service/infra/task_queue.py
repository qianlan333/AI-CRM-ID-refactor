from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

task_logger = logging.getLogger("task_queue")

_rq_queue = None
_rq_available = False
_thread_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wecom-bg")


def _try_init_rq(redis_url: str) -> bool:
    global _rq_queue, _rq_available
    try:
        from redis import Redis
        from rq import Queue

        conn = Redis.from_url(redis_url)
        conn.ping()
        _rq_queue = Queue(connection=conn, default_timeout=300)
        _rq_available = True
        task_logger.info("RQ task queue initialized redis_url=%s", redis_url)
        return True
    except Exception as exc:
        _rq_available = False
        _rq_queue = None
        task_logger.warning("RQ unavailable, falling back to ThreadPoolExecutor: %s", exc)
        return False


def init_task_queue(app) -> None:
    redis_url = app.config.get("REDIS_URL", "").strip()
    if redis_url:
        _try_init_rq(redis_url)
    else:
        task_logger.info("REDIS_URL not configured, using ThreadPoolExecutor fallback")


def enqueue_task(
    task_fn: Callable,
    *args: Any,
    task_name: str = "",
    retry_max: int = 0,
    **kwargs: Any,
) -> str | None:
    label = task_name or getattr(task_fn, "__name__", "unknown")

    if _rq_available and _rq_queue is not None:
        try:
            job = _rq_queue.enqueue(
                task_fn,
                *args,
                **kwargs,
                job_timeout=300,
                retry=_build_rq_retry(retry_max) if retry_max else None,
                description=label,
            )
            task_logger.info("task enqueued via RQ task=%s job_id=%s", label, job.id)
            return job.id
        except Exception:
            task_logger.exception("RQ enqueue failed, falling back to thread task=%s", label)

    future = _thread_executor.submit(task_fn, *args, **kwargs)
    task_logger.info("task submitted to ThreadPoolExecutor task=%s", label)
    return None


def _build_rq_retry(max_retries: int):
    try:
        from rq import Retry
        return Retry(max=max_retries, interval=[30, 60, 120])
    except ImportError:
        return None


def get_queue_depth() -> int:
    if _rq_available and _rq_queue is not None:
        try:
            return len(_rq_queue)
        except Exception:
            return -1
    return _thread_executor._work_queue.qsize()


def is_rq_active() -> bool:
    return _rq_available
