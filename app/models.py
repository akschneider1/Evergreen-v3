"""SQLModel database table models and Pydantic data models for Evergreen v3."""

from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Database tables
# ---------------------------------------------------------------------------

class Run(SQLModel, table=True):
    """A single eval run triggered by a user."""

    id: str = Field(primary_key=True)
    name: str
    benchmark_id: str
    model: str
    status: str = "pending"          # pending | running | complete | failed
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"index": True})
    completed_at: Optional[datetime] = None
    pass_rate: Optional[float] = None
    limit: Optional[int] = None      # cap on samples evaluated; None = all
    error: Optional[str] = None
    report_html: Optional[str] = None


class TeamBenchmark(SQLModel, table=True):
    """A custom benchmark created by the team in the Eval Builder."""

    id: str = Field(primary_key=True)
    name: str
    description: str
    version: str = "1.0"
    tags: str = ""                   # comma-separated tag list
    use_cases: str = ""              # comma-separated use case list
    status: str = "draft"            # draft | published
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvalCase(SQLModel, table=True):
    """A single test case within a TeamBenchmark."""

    id: str = Field(primary_key=True)
    team_benchmark_id: str = Field(foreign_key="teambenchmark.id")
    question: str
    expected_answer: str
    context: Optional[str] = None
    metric: str = "accuracy"         # safety | accuracy | ease_of_use | effectiveness | emotion
    severity: str = "medium"         # low | medium | high | critical
    status: str = "draft"            # draft | ready | approved
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Pydantic models (non-table — for catalog and API shapes)
# ---------------------------------------------------------------------------

class BenchmarkEntry(BaseModel):
    """A benchmark entry loaded from a YAML file in catalog/benchmarks/."""

    id: str
    display_name: str
    description: str
    why_it_matters: str
    source: str
    inspect_task: str
    tags: list[str]
    use_cases: list[str]
    setup_required: bool
    cost_estimate: str
    time_estimate: str
    status: str


class JobStatus(BaseModel):
    """In-memory state for a running eval job."""

    job_id: str
    run_id: str
    step: str = "Starting..."
    percent: int = 0
    status: str = "pending"          # pending | running | complete | failed
    error: Optional[str] = None       # short user-facing message
    error_detail: Optional[str] = None  # full traceback for the debug dropdown
