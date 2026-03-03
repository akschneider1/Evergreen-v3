"""In-memory job state management for background eval runs."""

import time
from typing import Optional
from app.models import JobStatus

# ---------------------------------------------------------------------------
# In-memory store  {job_id: (JobStatus, created_at_epoch)}
# ---------------------------------------------------------------------------

_jobs: dict[str, tuple[JobStatus, float]] = {}
_TTL_SECONDS = 3600  # 1 hour
_MAX_JOBS = 200       # hard cap — evict oldest-first above this


def create_job(job_id: str, run_id: str) -> JobStatus:
    """Create and register a new job, returning its initial JobStatus.

    Runs TTL eviction and hard-cap eviction here so get_job() stays O(1).
    """
    _evict_expired()
    # If still over cap after TTL eviction, drop the oldest jobs
    if len(_jobs) >= _MAX_JOBS:
        oldest = sorted(_jobs.items(), key=lambda kv: kv[1][1])
        for jid, _ in oldest[:len(_jobs) - _MAX_JOBS + 1]:
            del _jobs[jid]

    job = JobStatus(job_id=job_id, run_id=run_id, step="Starting...", percent=0, status="pending")
    _jobs[job_id] = (job, time.time())
    return job


def update_job(job_id: str, *, step: str, percent: int, status: str = "running", error: Optional[str] = None, error_detail: Optional[str] = None) -> None:
    """Update step label, percent, and status for an existing job."""
    if job_id not in _jobs:
        return
    _, created_at = _jobs[job_id]
    updated = JobStatus(
        job_id=job_id,
        run_id=_jobs[job_id][0].run_id,
        step=step,
        percent=percent,
        status=status,
        error=error,
        error_detail=error_detail,
    )
    _jobs[job_id] = (updated, created_at)


def get_job(job_id: str) -> Optional[JobStatus]:
    """Return the current JobStatus, or None if not found or expired.

    O(1) — eviction is handled in create_job(), not here.
    A job that has passed TTL but hasn't been evicted yet will still be
    returned here; stale jobs are harmless (they show a terminal state).
    """
    entry = _jobs.get(job_id)
    return entry[0] if entry else None


def _evict_expired() -> None:
    """Remove jobs older than TTL."""
    now = time.time()
    expired = [jid for jid, (_, created_at) in _jobs.items() if now - created_at > _TTL_SECONDS]
    for jid in expired:
        del _jobs[jid]
