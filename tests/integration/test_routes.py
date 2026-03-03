"""Integration tests for all Evergreen v3 routes."""

import uuid
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Catalog / benchmark routes
# ---------------------------------------------------------------------------

def test_catalog_page_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200


def test_catalog_page_contains_benchmark_cards(client):
    response = client.get("/")
    assert "Truthfulness" in response.text or "benchmark" in response.text.lower()


def test_catalog_filter_by_tag(client):
    response = client.get("/?tag=safety")
    assert response.status_code == 200


def test_benchmark_detail_returns_partial(client):
    response = client.get("/benchmark/truthfulqa")
    assert response.status_code == 200
    assert "Truthfulness" in response.text


def test_benchmark_detail_404_for_unknown(client):
    response = client.get("/benchmark/does_not_exist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Run start
# ---------------------------------------------------------------------------

def test_run_start_redirects_to_progress(client, mock_runner):
    response = client.post("/run/start", data={
        "benchmark_id": "truthfulqa",
        "model": "gpt-4o",
        "run_name": "Test run",
    }, follow_redirects=False)
    assert response.status_code == 303
    assert "/progress" in response.headers["location"]


def test_run_start_invalid_benchmark(client):
    response = client.post("/run/start", data={
        "benchmark_id": "nonexistent",
        "model": "gpt-4o",
        "run_name": "Test run",
    })
    assert response.status_code == 400


def test_run_start_invalid_model(client):
    response = client.post("/run/start", data={
        "benchmark_id": "truthfulqa",
        "model": "gpt-999-turbo",
        "run_name": "Test run",
    })
    assert response.status_code == 400


def test_run_start_missing_name(client):
    response = client.post("/run/start", data={
        "benchmark_id": "truthfulqa",
        "model": "gpt-4o",
        "run_name": "  ",
    })
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Progress + status polling
# ---------------------------------------------------------------------------

def test_progress_page_returns_200(client, mock_runner, db):
    from app.core import jobs as job_store
    job_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    job_store.create_job(job_id, run_id)

    response = client.get(f"/run/{job_id}/progress")
    assert response.status_code == 200


def test_status_partial_returns_html(client, mock_runner, db):
    from app.core import jobs as job_store
    job_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    job_store.create_job(job_id, run_id)
    job_store.update_job(job_id, step="Running...", percent=50)

    response = client.get(f"/run/{job_id}/status")
    assert response.status_code == 200
    assert "Running" in response.text or "50" in response.text


def test_status_partial_unknown_job(client):
    response = client.get(f"/run/{uuid.uuid4()}/status")
    assert response.status_code == 200  # renders error partial, not 404


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def test_report_returns_html(client, sample_run):
    response = client.get(f"/run/{sample_run.id}/report")
    assert response.status_code == 200
    assert "Summary" in response.text
    assert "Analysis" in response.text
    assert "Details" in response.text


def test_report_404_for_unknown_run(client):
    response = client.get(f"/run/{uuid.uuid4()}/report")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def test_history_page_returns_200(client):
    response = client.get("/history")
    assert response.status_code == 200


def test_history_page_shows_runs(client, sample_run):
    response = client.get("/history")
    assert sample_run.name in response.text


# ---------------------------------------------------------------------------
# Team Library (M2 routes)
# ---------------------------------------------------------------------------

def test_library_page_returns_200(client):
    response = client.get("/library")
    assert response.status_code == 200


def test_create_benchmark_redirects(client):
    response = client.post("/library", data={
        "name": "Test Benchmark",
        "description": "A test",
        "tags": "safety",
        "use_cases": "general",
    }, follow_redirects=False)
    assert response.status_code == 303
    assert "/library/" in response.headers["location"]


def test_create_benchmark_persisted(client, db):
    client.post("/library", data={
        "name": "Persisted Benchmark",
        "description": "testing persistence",
        "tags": "",
        "use_cases": "",
    })
    from sqlmodel import select
    from app.models import TeamBenchmark
    result = db.exec(select(TeamBenchmark).where(TeamBenchmark.name == "Persisted Benchmark")).first()
    assert result is not None


def test_builder_page_returns_200(client):
    # Create a benchmark first
    response = client.post("/library", data={
        "name": "Builder Test",
        "description": "x",
        "tags": "",
        "use_cases": "",
    }, follow_redirects=False)
    benchmark_id = response.headers["location"].split("/library/")[1]
    response = client.get(f"/library/{benchmark_id}")
    assert response.status_code == 200


def test_add_case_returns_row_partial(client):
    # Create benchmark
    r = client.post("/library", data={
        "name": "Case Test",
        "description": "x",
        "tags": "",
        "use_cases": "",
    }, follow_redirects=False)
    benchmark_id = r.headers["location"].split("/library/")[1]

    # Add case
    response = client.post(f"/library/{benchmark_id}/cases", data={
        "question": "Is this safe?",
        "expected_answer": "Yes",
        "context": "",
        "metric": "safety",
        "severity": "high",
    })
    assert response.status_code == 200
    assert "Is this safe?" in response.text


def test_publish_benchmark(client, db):
    # Create + add case + publish
    r = client.post("/library", data={
        "name": "Publish Test",
        "description": "x",
        "tags": "",
        "use_cases": "",
    }, follow_redirects=False)
    benchmark_id = r.headers["location"].split("/library/")[1]

    client.post(f"/library/{benchmark_id}/cases", data={
        "question": "Q?", "expected_answer": "A",
        "context": "", "metric": "accuracy", "severity": "medium",
    })

    r = client.post(f"/library/{benchmark_id}/publish", follow_redirects=False)
    assert r.status_code == 303

    from sqlmodel import select
    from app.models import TeamBenchmark
    b = db.get(TeamBenchmark, benchmark_id)
    assert b.status == "published"
