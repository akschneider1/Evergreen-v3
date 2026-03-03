"""Routes: run progress polling, report serving, history, and export."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from sqlmodel import Session, select

from app.main import get_db, templates
from app.core import jobs as job_store
from app.models import Run

router = APIRouter()


@router.get("/run/{job_id}/progress", response_class=HTMLResponse)
async def progress_page(request: Request, job_id: str):
    """Progress page — HTMX polls /run/{job_id}/status every 2 seconds."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run not found")
    return templates.TemplateResponse("run_progress.html", {
        "request": request,
        "job_id": job_id,
        "job": job,
    })


@router.get("/run/{job_id}/status", response_class=HTMLResponse)
async def run_status(request: Request, job_id: str):
    """HTMX partial — called every 2s by the progress page."""
    job = job_store.get_job(job_id)
    if not job:
        # Job expired or not found — render a terminal error state
        return templates.TemplateResponse("partials/run_status.html", {
            "request": request,
            "job": None,
            "job_id": job_id,
        })
    return templates.TemplateResponse("partials/run_status.html", {
        "request": request,
        "job": job,
        "job_id": job_id,
    })


@router.get("/run/{job_id}/report", response_class=HTMLResponse)
async def view_report(job_id: str, db: Session = Depends(get_db)):
    """Serve the completed HTML report for a run."""
    job = job_store.get_job(job_id)
    run_id = job.run_id if job else job_id  # fall back to treating job_id as run_id

    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Report not found")
    if run.status != "complete" or not run.report_html:
        raise HTTPException(status_code=404, detail="Report not yet available")

    return HTMLResponse(content=run.report_html)


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, db: Session = Depends(get_db)):
    """Run history page — all past runs for the team."""
    runs = db.exec(select(Run).order_by(Run.created_at.desc()).limit(100)).all()
    return templates.TemplateResponse("history.html", {
        "request": request,
        "runs": runs,
    })


@router.get("/run/{job_id}/export/html")
async def export_html(job_id: str, db: Session = Depends(get_db)):
    """Download the report as a self-contained HTML file."""
    job = job_store.get_job(job_id)
    run_id = job.run_id if job else job_id

    run = db.get(Run, run_id)
    if not run or not run.report_html:
        raise HTTPException(status_code=404, detail="Report not found")

    filename = f"evergreen-report-{run.name.lower().replace(' ', '-')}.html"
    return Response(
        content=run.report_html,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/run/{job_id}/export/pdf")
async def export_pdf(job_id: str, db: Session = Depends(get_db)):
    """Generate and stream a PDF version of the report."""
    try:
        from weasyprint import HTML as WeasyprintHTML
    except ImportError:
        raise HTTPException(status_code=501, detail="PDF export requires weasyprint")

    job = job_store.get_job(job_id)
    run_id = job.run_id if job else job_id

    run = db.get(Run, run_id)
    if not run or not run.report_html:
        raise HTTPException(status_code=404, detail="Report not found")

    pdf_bytes = WeasyprintHTML(string=run.report_html).write_pdf()
    filename = f"evergreen-report-{run.name.lower().replace(' ', '-')}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
