"""Evergreen v3 CLI — launch the web app or run evaluations from the terminal."""

import typer
from typing import Optional

app = typer.Typer(help="Evergreen v3 — AI evaluation platform for government teams.")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8080, help="Port to bind"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (development)"),
):
    """Launch the Evergreen web application."""
    import uvicorn
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


@app.command()
def run(
    benchmark_id: str = typer.Argument(..., help="Benchmark ID from the catalog (e.g. truthfulqa)"),
    model: str = typer.Option("gpt-4o", "--model", "-m", help="Model to evaluate"),
    name: str = typer.Option("", "--name", "-n", help="Run name (defaults to benchmark + model)"),
):
    """Run a benchmark evaluation from the command line (no web UI required)."""
    import asyncio
    from sqlmodel import Session, create_engine
    from sqlmodel import SQLModel
    from app.core.catalog import get_benchmark, load_catalog
    from app.core.runner import MODEL_MAP, run_benchmark
    from app.core import jobs as job_store
    from app.models import Run
    import uuid, os
    from dotenv import load_dotenv
    load_dotenv()

    load_catalog()
    benchmark = get_benchmark(benchmark_id)
    if not benchmark:
        typer.echo(f"Error: benchmark '{benchmark_id}' not found. Run `evergreen catalog list` to see available benchmarks.", err=True)
        raise typer.Exit(1)
    if model not in MODEL_MAP:
        typer.echo(f"Error: model '{model}' not recognised. Choose from: {', '.join(MODEL_MAP)}", err=True)
        raise typer.Exit(1)

    run_name = name.strip() or f"{benchmark.display_name} — {model}"
    run_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    import pathlib
    _db_path = pathlib.Path(__file__).parent / "evergreen.db"
    DATABASE_URL = f"sqlite:///{_db_path}"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as db:
        eval_run = Run(id=run_id, name=run_name, benchmark_id=benchmark_id, model=model)
        db.add(eval_run)
        db.commit()
        job_store.create_job(job_id, run_id)

        typer.echo(f"Starting: {run_name}")
        typer.echo(f"Benchmark: {benchmark.display_name}")
        typer.echo(f"Model: {MODEL_MAP[model]}")
        typer.echo("")

        async def _run():
            await run_benchmark(eval_run, job_id, db)

        asyncio.run(_run())

        job = job_store.get_job(job_id)
        if job and job.status == "complete":
            typer.echo(f"✓ Complete — pass rate: {round((eval_run.pass_rate or 0) * 100)}%")
            typer.echo(f"  Report saved to database (run ID: {run_id})")
        else:
            typer.echo(f"✗ Failed: {job.error if job else 'unknown error'}", err=True)
            raise typer.Exit(1)


@app.command("catalog")
def catalog_list(
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by tag"),
):
    """List available benchmarks in the catalog."""
    from app.core.catalog import filter_benchmarks, load_catalog
    from dotenv import load_dotenv
    load_dotenv()

    load_catalog()
    tags = [tag] if tag else None
    benchmarks = filter_benchmarks(tags=tags)

    if not benchmarks:
        typer.echo("No benchmarks found.")
        return

    typer.echo(f"{'ID':<22} {'Display Name':<35} {'Tags':<35} {'Cost':<8} Time")
    typer.echo("—" * 110)
    for b in benchmarks:
        typer.echo(f"{b.id:<22} {b.display_name:<35} {', '.join(b.tags):<35} {b.cost_estimate:<8} {b.time_estimate}")


if __name__ == "__main__":
    app()
