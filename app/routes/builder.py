"""Routes: Team Library and Eval Builder (Milestone 2)."""

import uuid
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.main import get_db, templates
from app.models import TeamBenchmark, EvalCase

router = APIRouter()


@router.get("/library", response_class=HTMLResponse)
async def library_page(request: Request, db: Session = Depends(get_db)):
    """Team Library — list of team-created benchmarks."""
    benchmarks = db.exec(select(TeamBenchmark).order_by(TeamBenchmark.created_at.desc())).all()
    return templates.TemplateResponse("library.html", {
        "request": request,
        "benchmarks": benchmarks,
    })


@router.get("/library/new", response_class=HTMLResponse)
async def new_benchmark_form(request: Request):
    """Form to create a new team benchmark."""
    return templates.TemplateResponse("builder.html", {
        "request": request,
        "benchmark": None,
        "cases": [],
    })


@router.post("/library")
async def create_benchmark(
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(...),
    tags: str = Form(""),
    use_cases: str = Form(""),
):
    """Create a new TeamBenchmark and redirect to its builder page."""
    if not name.strip():
        raise HTTPException(status_code=400, detail="Benchmark name is required")

    benchmark = TeamBenchmark(
        id=str(uuid.uuid4()),
        name=name.strip(),
        description=description.strip(),
        tags=tags.strip(),
        use_cases=use_cases.strip(),
    )
    db.add(benchmark)
    db.commit()
    return RedirectResponse(url=f"/library/{benchmark.id}", status_code=303)


@router.get("/library/{benchmark_id}", response_class=HTMLResponse)
async def builder_page(request: Request, benchmark_id: str, db: Session = Depends(get_db)):
    """Eval Builder — edit test cases for a team benchmark."""
    benchmark = db.get(TeamBenchmark, benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    cases = db.exec(
        select(EvalCase)
        .where(EvalCase.team_benchmark_id == benchmark_id)
        .order_by(EvalCase.created_at)
    ).all()
    return templates.TemplateResponse("builder.html", {
        "request": request,
        "benchmark": benchmark,
        "cases": cases,
    })


@router.post("/library/{benchmark_id}/cases", response_class=HTMLResponse)
async def add_case(
    request: Request,
    benchmark_id: str,
    db: Session = Depends(get_db),
    question: str = Form(...),
    expected_answer: str = Form(...),
    context: str = Form(""),
    metric: str = Form("accuracy"),
    severity: str = Form("medium"),
):
    """Add a test case to a benchmark, return updated row partial."""
    benchmark = db.get(TeamBenchmark, benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    case = EvalCase(
        id=str(uuid.uuid4()),
        team_benchmark_id=benchmark_id,
        question=question.strip(),
        expected_answer=expected_answer.strip(),
        context=context.strip() or None,
        metric=metric,
        severity=severity,
    )
    db.add(case)
    db.commit()

    return templates.TemplateResponse("partials/case_row.html", {
        "request": request,
        "case": case,
    })


@router.post("/library/{benchmark_id}/publish")
async def publish_benchmark(benchmark_id: str, db: Session = Depends(get_db)):
    """Publish a benchmark so it appears in the catalog alongside built-in entries."""
    benchmark = db.get(TeamBenchmark, benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    case_count = len(db.exec(
        select(EvalCase).where(EvalCase.team_benchmark_id == benchmark_id)
    ).all())
    if case_count == 0:
        raise HTTPException(status_code=400, detail="Add at least one test case before publishing")

    benchmark.status = "published"
    db.add(benchmark)
    db.commit()
    return RedirectResponse(url=f"/library/{benchmark_id}", status_code=303)
