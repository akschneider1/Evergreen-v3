"""Async wrapper around the Inspect eval engine."""

import asyncio
import tempfile
import traceback

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


def _classify_error(exc: Exception) -> str:
    """Return a short, user-friendly error message based on the exception type."""
    msg = str(exc)
    low = msg.lower()

    if any(k in msg for k in ("Hub", "snapshot folder", "locate the files on the Hub")):
        return (
            "Dataset download failed: could not reach Hugging Face Hub. "
            "This is usually a transient network issue — try running again. "
            "If it keeps failing, try a benchmark that doesn't require dataset downloads "
            "(IFEval, StrongREJECT, CoCoNot, or AgentHarm work offline)."
        )
    if "api_key" in low or "apikey" in low or "authentication" in low or "unauthorized" in low or "invalid x-api-key" in low:
        return (
            "API key error: the model provider rejected the request. "
            "Check that the correct API key is set in your Replit Secrets "
            "(OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY)."
        )
    if "rate limit" in low or "ratelimit" in low or "429" in msg:
        return (
            "Rate limit hit: the model provider is throttling requests. "
            "Wait a minute and try again, or switch to a different model."
        )
    if "timeout" in low or "timed out" in low:
        return (
            "The evaluation timed out. The benchmark may be too large for this run. "
            "Try again or contact support if this persists."
        )
    if "no module named" in low or "importerror" in low or "modulenotfounderror" in low:
        return f"Missing dependency: {msg}. The Replit environment may need a redeploy."
    # Fallback — include the raw message so it's not a black box
    return msg if len(msg) <= 300 else msg[:297] + "..."


def _load_task(inspect_task: str):
    """Load an Inspect task by importing from its submodule.

    inspect_task format: "inspect_evals/bbq" → imports inspect_evals.bbq.bbq()
    """
    import importlib

    if "/" in inspect_task:
        package, name = inspect_task.split("/", 1)
        func_name = name.replace("-", "_")
        mod = importlib.import_module(f"{package}.{func_name}")
        task_fn = getattr(mod, func_name)
        return task_fn()
    raise ValueError(f"Unsupported inspect_task format: {inspect_task}")


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

        # Step 2 — load the Inspect task object
        job_store.update_job(job_id, step="Preparing evaluation...", percent=15, status="running")
        task = _load_task(benchmark.inspect_task)

        # Step 3 — run eval in thread pool (inspect_eval is blocking)
        job_store.update_job(job_id, step="Connecting to model...", percent=25, status="running")

        with tempfile.TemporaryDirectory() as tmp_dir:
            job_store.update_job(
                job_id,
                step="Running evaluations — this may take a few minutes...",
                percent=35,
                status="running",
            )
            logs = await asyncio.to_thread(
                inspect_eval,
                task,
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
        tb = traceback.format_exc()
        run.status = "failed"
        run.error = tb  # full traceback stored in DB
        db.add(run)
        db.commit()
        job_store.update_job(
            job_id,
            step="Evaluation failed",
            percent=0,
            status="failed",
            error=_classify_error(exc),
            error_detail=tb,
        )
        raise


