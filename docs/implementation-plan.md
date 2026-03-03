# Evergreen v3 — Implementation Plan

## Context

Evergreen v3 is a new Python web platform wrapping UK AISI's Inspect evaluation framework for non-technical state government staff. The goal is a browser-based tool where users can run AI safety/capability benchmarks and build custom evaluations without writing code or using a CLI. Deployed on Replit, open source.

There is **no existing Python code** — this is a clean build. The current workspace has only `CLAUDE.md`, `PLAN.md` (research doc, not a spec), `README.md`, and a `.replit` configured for Node.js that needs to be updated to Python.

---

## Architecture overview

```
Browser (Tailwind + DaisyUI + HTMX)
    ↕ HTMX partial updates
FastAPI (Jinja2 templates)
    ├── Benchmark Catalog (YAML-driven registry)
    ├── Run Pipeline (Inspect → EvalLog → Report)
    ├── Eval Builder (Team Library)
    └── Run History (SQLite)
```

---

## Milestones

### Milestone 1 — Benchmark catalog + run pipeline (ships first)
Users can browse a curated benchmark catalog, run a benchmark against a model, see real-time progress, and view a report. No test case authoring needed.

### Milestone 2 — Eval Builder + Team Library
Users can build custom test case packs, review and approve cases, publish them as reusable team benchmarks, and run them like any catalog entry.

---

## Step-by-step implementation

### Step 1: Project setup

**File: `.replit`**
Update from Node.js to Python 3.11:
```toml
run = "uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload"
modules = ["python-3.11"]
```

**File: `pyproject.toml`**
```toml
[project]
name = "evergreen-v3"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",   # form parsing
    "sqlmodel>=0.0.21",
    "pydantic>=2.8",
    "pyyaml>=6.0",
    "jsonschema>=4.23",
    "httpx>=0.27",               # async HTTP + test client
    "typer>=0.12",
    "python-dotenv>=1.0",
    "inspect-ai>=0.3",
    "inspect-evals>=0.4",
    "weasyprint>=62",            # PDF export
]

[project.scripts]
evergreen = "cli:app"
```

**File: `.env.example`**
```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
DATABASE_URL=sqlite:///./evergreen.db
```

---

### Step 2: Benchmark catalog — schema and entries

**File: `catalog/schema.yaml`**
JSON Schema for every benchmark entry. Required fields:
- `id` (string, unique)
- `display_name` (string)
- `description` (string, ≤ 160 chars — shown on catalog card)
- `why_it_matters` (string — plain language, no jargon)
- `source` (enum: `inspect_evals`, `team_library`, `custom`)
- `inspect_task` (string — e.g. `inspect_evals/truthfulqa`)
- `tags` (array: safety | fairness | accuracy | reasoning | instruction_following)
- `use_cases` (array: benefits_delivery | public_safety | general)
- `setup_required` (bool — false = zero-config)
- `cost_estimate` (enum: low | medium | high)
- `time_estimate` (string — e.g. "5–10 min")
- `status` (enum: active | coming_soon | deprecated)

**Initial benchmark entries (10 YAML files in `catalog/benchmarks/`):**

| File | Display name | Tags | Use cases |
|---|---|---|---|
| `truthfulqa.yaml` | Truthfulness & Hallucination | accuracy, safety | benefits_delivery |
| `ifeval.yaml` | Instruction Following | instruction_following | benefits_delivery |
| `bbq.yaml` | Bias & Fairness (BBQ) | fairness | benefits_delivery |
| `simpleqa.yaml` | Factual Accuracy (SimpleQA) | accuracy | benefits_delivery |
| `strong_reject.yaml` | Jailbreak Resistance | safety | public_safety |
| `coconot.yaml` | Contextual Compliance | safety | public_safety |
| `agentharm.yaml` | Harm Prevention (AgentHarm) | safety | public_safety |
| `mmlu_0_shot.yaml` | General Knowledge (MMLU) | reasoning | general |
| `arc_challenge.yaml` | Reasoning (ARC Challenge) | reasoning | general |
| `bbh.yaml` | Complex Reasoning (BIG-Bench Hard) | reasoning | general |

---

### Step 3: Core modules

**File: `app/core/catalog.py`**
- `load_catalog() → list[BenchmarkEntry]`: reads all YAML files from `catalog/benchmarks/`, validates each against schema, returns sorted list
- `get_benchmark(id: str) → BenchmarkEntry | None`
- `filter_benchmarks(tags, use_cases, status) → list[BenchmarkEntry]`
- Catalog is loaded once at app startup and cached; no DB needed

**File: `app/models.py`** — SQLModel models
```python
class Run(SQLModel, table=True):
    id: str          # UUID
    name: str
    benchmark_id: str
    model: str
    status: str      # pending | running | complete | failed
    created_at: datetime
    completed_at: datetime | None
    pass_rate: float | None
    error: str | None
    report_html: str | None   # stored as text in DB for simplicity

class EvalCase(SQLModel, table=True):
    id: str
    team_benchmark_id: str
    question: str
    expected_answer: str
    context: str | None
    metric: str        # safety | accuracy | ease_of_use | effectiveness | emotion
    severity: str      # low | medium | high | critical
    status: str        # draft | ready | approved
    created_by: str | None

class TeamBenchmark(SQLModel, table=True):
    id: str
    name: str
    description: str
    version: str
    tags: str          # comma-separated (SQLite-simple)
    use_cases: str     # comma-separated
    status: str        # draft | published
    created_at: datetime
```

**File: `app/core/jobs.py`**
- In-memory dict `{job_id: JobStatus}` for active/recent runs (TTL 1 hour)
- `JobStatus`: id, step (str), percent (int), status, error
- Steps: "Loading benchmark..." → "Connecting to model..." → "Running evaluations (N of M)..." → "Generating report..." → "Complete"
- `create_job(run_id) → str`
- `update_job(job_id, step, percent)`
- `get_job(job_id) → JobStatus | None`

**File: `app/core/runner.py`**
```python
async def run_benchmark(run: Run, job_id: str) -> str:
    """Execute an Inspect eval. Returns HTML report string."""
    # 1. Load the task from inspect_evals
    task = _load_inspect_task(run.benchmark_id)
    # 2. Run in thread pool (inspect eval() is blocking)
    log = await asyncio.to_thread(
        inspect_eval, task, model=run.model, log_dir=tmp_dir
    )
    # 3. Map EvalLog → report HTML
    return await map_to_report(log[0], run)
```
- Uses `asyncio.to_thread()` — never blocks the event loop
- Progress updates injected via callback or by polling log file

**File: `app/core/mapper.py`**
- `map_to_report(log: EvalLog, run: Run) → ReportData`
- Extracts: overall pass rate, per-sample results, scorer explanations, token usage
- `render_report(data: ReportData) → str` — returns self-contained HTML string (3-tab structure)

---

### Step 4: Routes

**File: `app/routes/benchmarks.py`**
- `GET /` → catalog page (Jinja2, full page)
- `GET /benchmark/{id}` → HTMX partial: benchmark detail panel
- `POST /run/start` → validate form, create Run + job, launch BackgroundTask, return redirect to `/run/{job_id}/progress`

**File: `app/routes/runs.py`**
- `GET /run/{job_id}/progress` → progress page (Jinja2, full page with HTMX polling)
- `GET /run/{job_id}/status` → HTMX partial: status update (called every 2s by progress page)
- `GET /run/{job_id}/report` → serve report HTML (stored in DB)
- `GET /history` → run history page
- `GET /run/{job_id}/export/pdf` → generate + stream PDF (WeasyPrint)
- `GET /run/{job_id}/export/html` → download self-contained HTML

**File: `app/routes/builder.py`** (Milestone 2)
- `GET /library` → team library page
- `GET /library/new` → new benchmark form
- `POST /library` → create TeamBenchmark
- `GET /library/{id}` → builder editor (test case table)
- `POST /library/{id}/cases` → add/update EvalCase
- `POST /library/{id}/publish` → set status=published, appear in catalog

**File: `app/main.py`**
```python
app = FastAPI(lifespan=lifespan)  # lifespan: DB init + catalog load
app.include_router(benchmarks.router)
app.include_router(runs.router)
app.include_router(builder.router)
app.mount("/static", StaticFiles(directory="app/static"))
templates = Jinja2Templates(directory="app/templates")
```

---

### Step 5: Templates

All templates use Tailwind + DaisyUI. HTMX loaded via CDN. Base layout in `base.html`.

| Template | Route | Notes |
|---|---|---|
| `catalog.html` | `GET /` | Cards grid with tag filter buttons; "Recommended" section pinned top |
| `benchmark_detail.html` | HTMX partial | Slide-in panel with full description + Run button |
| `run_configure.html` | after card click | Model selector, run name, cost/time estimate, "More options" collapse |
| `run_progress.html` | `GET /run/{id}/progress` | HTMX polling `hx-get="/run/{id}/status" hx-trigger="every 2s"` |
| `run_status.html` | HTMX partial | Progress bar + step label; swaps to redirect on complete |
| `report.html` | `GET /run/{id}/report` | 3-tab (Summary / Analysis / Details); export buttons |
| `history.html` | `GET /history` | Sortable table of past runs |
| `library.html` | `GET /library` | Team benchmarks list + "New" button |
| `builder.html` | `GET /library/{id}` | Editable test case table (HTMX row add/edit) |

**Key UX decisions baked into templates:**
- Model selector shows human names: "GPT-4o (OpenAI)", "Claude Sonnet 4 (Anthropic)" — not API strings
- Cost estimate displayed as: "Estimated cost: < $1 · Estimated time: 5–10 min"
- Progress step labels are plain English: "Running your evaluation (12 of 20 questions complete)..."
- Report tab 1 (Summary) contains no technical terms; tab 3 (Details) is explicitly labeled "For technical staff"

---

### Step 6: CLI

**File: `cli.py`** — Typer app
```
evergreen serve          # launch web app (uvicorn)
evergreen run <benchmark_id> --model openai/gpt-4o  # CLI eval (no web UI)
evergreen catalog list   # list available benchmarks
```

---

### Step 7: Tests

**File: `tests/conftest.py`**
- `test_app` fixture: FastAPI TestClient with in-memory SQLite
- `mock_runner` fixture: patches `app.core.runner.run_benchmark` to return fixture HTML
- `sample_catalog` fixture: 2-3 benchmark YAML fixtures in temp dir
- `sample_run` fixture: a completed Run in DB

**File: `tests/unit/test_catalog.py`**
- Valid YAML loads correctly
- Missing required field raises validation error
- `filter_benchmarks()` filters by tag and use_case correctly
- `setup_required=true` entries excluded from active catalog

**File: `tests/unit/test_mapper.py`**
- Mock `EvalLog` with 3 samples → `ReportData` has correct pass_rate
- Failed samples appear in Analysis tab data
- Missing scorer in log doesn't crash mapper

**File: `tests/integration/test_routes.py`**
- `GET /` returns 200, contains benchmark cards
- `POST /run/start` with valid form → 303 redirect to progress page
- `GET /run/{id}/status` returns HTMX partial with status
- `GET /run/{id}/report` returns HTML with 3 tab labels
- `GET /history` returns 200
- `POST /library` creates TeamBenchmark in DB

**CI: `.github/workflows/ci.yml`**
```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.11" }
- run: pip install -e ".[dev]"
- run: pytest tests/ -v --tb=short
```

---

## File creation order

1. `.replit` + `pyproject.toml` + `.env.example` + `.gitignore`
2. `catalog/schema.yaml`
3. `catalog/benchmarks/*.yaml` (10 files)
4. `app/__init__.py` + `app/main.py` (skeleton)
5. `app/models.py`
6. `app/core/catalog.py`
7. `app/core/jobs.py`
8. `app/core/runner.py`
9. `app/core/mapper.py`
10. `app/routes/benchmarks.py` + `app/routes/runs.py`
11. `app/templates/base.html` + all page templates
12. `cli.py`
13. `tests/conftest.py` + unit + integration tests
14. `app/routes/builder.py` + `app/templates/builder.html` + `app/templates/library.html` (Milestone 2)
15. `README.md` (deploy guide + contributing)
16. `CHANGELOG.md`

---

## Verification

1. `pytest tests/ -v` passes with no API calls (all mocked)
2. Start app with `uvicorn app.main:app --reload`; visit `/` — catalog loads with 10 benchmark cards
3. Click a benchmark → detail panel slides in with description and "Run" button
4. Submit run form → redirected to progress page; HTMX polls status every 2s
5. Run completes → report page shows 3 tabs with readable content
6. `/history` shows completed run in table with link to report
7. Export PDF downloads a file with Summary tab content
