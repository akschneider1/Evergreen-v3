"""Routes: benchmark catalog browse and run trigger."""

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.main import get_db, templates
from app.core.catalog import filter_benchmarks, get_benchmark
from app.core.runner import MODEL_MAP, run_benchmark
from app.core import jobs as job_store
from app.models import Run

router = APIRouter()

# Human-friendly model choices shown in the UI
UI_MODELS = [
    ("gpt-4o", "GPT-4o (OpenAI)"),
    ("gpt-4o-mini", "GPT-4o mini (OpenAI) — faster, lower cost"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6 (Anthropic)"),
    ("claude-haiku-4-5", "Claude Haiku 4.5 (Anthropic) — faster, lower cost"),
    ("gemini-2.0-flash", "Gemini 2.0 Flash (Google)"),
]

TAG_LABELS = [
    ("safety", "Safety"),
    ("fairness", "Fairness"),
    ("accuracy", "Accuracy"),
    ("reasoning", "Reasoning"),
    ("instruction_following", "Instruction Following"),
]


@router.get("/", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    tag: Optional[str] = None,
    use_case: Optional[str] = None,
):
    """Main catalog page — browse and filter benchmarks."""
    tags = [tag] if tag else None
    use_cases = [use_case] if use_case else None
    benchmarks = filter_benchmarks(tags=tags, use_cases=use_cases)

    # Pinned "recommended" set always shown at top
    recommended_ids = {"truthfulqa", "bbq", "ifeval", "strong_reject"}
    recommended = [b for b in benchmarks if b.id in recommended_ids]
    rest = [b for b in benchmarks if b.id not in recommended_ids]

    return templates.TemplateResponse("catalog.html", {
        "request": request,
        "recommended": recommended,
        "benchmarks": rest,
        "tag_labels": TAG_LABELS,
        "active_tag": tag,
        "active_use_case": use_case,
    })


@router.get("/benchmark/{benchmark_id}", response_class=HTMLResponse)
async def benchmark_detail(request: Request, benchmark_id: str):
    """HTMX partial — benchmark detail panel."""
    benchmark = get_benchmark(benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return templates.TemplateResponse("partials/benchmark_detail.html", {
        "request": request,
        "benchmark": benchmark,
        "ui_models": UI_MODELS,
    })


@router.post("/run/start")
async def start_run(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    benchmark_id: str = Form(...),
    model: str = Form(...),
    run_name: str = Form(...),
    limit: Optional[int] = Form(None),
):
    """Validate form, create Run + job, kick off background eval, redirect to progress."""
    benchmark = get_benchmark(benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=400, detail="Invalid benchmark selected")
    if model not in MODEL_MAP:
        raise HTTPException(status_code=400, detail="Invalid model selected")
    if not run_name.strip():
        raise HTTPException(status_code=400, detail="Run name is required")

    run_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    # Clamp limit to a sane range; 0 or negative = run all
    safe_limit = limit if (limit and limit > 0) else None

    run = Run(
        id=run_id,
        name=run_name.strip(),
        benchmark_id=benchmark_id,
        model=model,
        limit=safe_limit,
    )
    db.add(run)
    db.commit()

    job_store.create_job(job_id, run_id)
    # Pass only IDs — runner creates its own DB session to avoid
    # using a closed request-scoped session mid-eval.
    background_tasks.add_task(run_benchmark, run_id, job_id)

    return RedirectResponse(url=f"/run/{job_id}/progress", status_code=303)
