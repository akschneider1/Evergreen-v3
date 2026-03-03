"""Async wrapper around the Inspect eval engine."""

import asyncio
import tempfile

from sqlmodel import Session

from app.models import Run
from app.core import jobs as job_store
from app.core.mapper import map_to_report, render_report


# ---------------------------------------------------------------------------
# Model name mapping: human-friendly UI value → Inspect model string
# ---------------------------------------------------------------------------

MODEL_MAP: dict[str, str] = {
    "gpt-4o": "openai/gpt-4o",
    "gpt-4o-mini": "openai/gpt-4o-mini",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4-6",
    "claude-haiku-4-5": "anthropic/claude-haiku-4-5-20251001",
    "gemini-2.0-flash": "google/gemini-2.0-flash",
}


async def run_benchmark(run: Run, job_id: str, db: Session) -> None:
    """Execute an Inspect eval for the given Run, save HTML report to DB.

    Runs in a background task — never blocks the event loop.
    Updates job state at each step so the progress page can poll it.
    """
    from inspect_ai import eval as inspect_eval  # deferred to avoid startup cost
    from app.core.catalog import get_benchmark

    try:
        # Step 1 — resolve benchmark and model
        job_store.update_job(job_id, step="Loading benchmark...", percent=5, status="running")
        benchmark = get_benchmark(run.benchmark_id)
        if benchmark is None:
            raise ValueError(f"Benchmark not found: {run.benchmark_id}")

        inspect_model = MODEL_MAP.get(run.model, run.model)

        # Step 2 — run eval in thread pool (inspect_eval is blocking)
        # Pass the task string directly — Inspect resolves it via its own
        # task registry, the same way the CLI does. No manual import needed.
        job_store.update_job(job_id, step="Connecting to model...", percent=20, status="running")

        with tempfile.TemporaryDirectory() as tmp_dir:
            job_store.update_job(
                job_id,
                step="Running evaluations — this may take a few minutes...",
                percent=30,
                status="running",
            )
            logs = await asyncio.to_thread(
                inspect_eval,
                benchmark.inspect_task,
                model=inspect_model,
                log_dir=tmp_dir,
            )

        # Step 4 — map results to report
        job_store.update_job(job_id, step="Generating report...", percent=85, status="running")
        log = logs[0]
        report_data = map_to_report(log, run)
        report_html = render_report(report_data)

        # Step 5 — persist
        job_store.update_job(job_id, step="Saving results...", percent=95, status="running")
        from datetime import datetime
        run.status = "complete"
        run.completed_at = datetime.utcnow()
        run.pass_rate = report_data.overall_pass_rate
        run.report_html = report_html
        db.add(run)
        db.commit()

        job_store.update_job(job_id, step="Complete", percent=100, status="complete")

    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        db.add(run)
        db.commit()
        job_store.update_job(
            job_id,
            step="Evaluation failed",
            percent=0,
            status="failed",
            error=str(exc),
        )
        raise


