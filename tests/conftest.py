"""Shared pytest fixtures for Evergreen v3 tests."""

import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, StaticPool

# ---------------------------------------------------------------------------
# Override DB to in-memory SQLite before importing the app
# ---------------------------------------------------------------------------

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("OPENAI_API_KEY", "test-key")


@pytest.fixture(name="engine", scope="session")
def engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="db")
def db_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(engine, tmp_path):
    """TestClient with in-memory DB and mocked catalog."""

    # Point app at in-memory engine
    import app.main as main_mod
    main_mod.engine = engine

    # Warm a minimal catalog from real YAML files
    from app.core import catalog as cat_mod
    cat_mod.load_catalog()

    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(name="mock_runner")
def mock_runner_fixture():
    """Patch run_benchmark so tests never call real Inspect or LLM APIs."""
    async def _fake_run(run, job_id, db):
        from app.core import jobs as job_store
        from datetime import datetime
        job_store.update_job(job_id, step="Complete", percent=100, status="complete")
        run.status = "complete"
        run.completed_at = datetime.utcnow()
        run.pass_rate = 0.8
        run.report_html = "<html><body><p>Summary</p><p>Analysis</p><p>Details (Technical)</p></body></html>"
        db.add(run)
        db.commit()

    with patch("app.routes.benchmarks.run_benchmark", side_effect=_fake_run):
        yield


@pytest.fixture(name="sample_run")
def sample_run_fixture(db):
    """A completed Run already in the DB."""
    from app.models import Run
    from datetime import datetime
    run = Run(
        id=str(uuid.uuid4()),
        name="Test run",
        benchmark_id="truthfulqa",
        model="gpt-4o",
        status="complete",
        pass_rate=0.75,
        report_html="<html><body><p>Summary</p><p>Analysis</p><p>Details (Technical)</p></body></html>",
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    return run
