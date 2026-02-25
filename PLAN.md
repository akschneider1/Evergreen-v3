# Evergreen v3 — Implementation Plan

## Context

Evergreen v2 is a pre-deployment AI evaluation tool for non-technical public sector users. It wraps **Promptfoo** (JS-based eval engine) with a Google Sheets input, Express web app, and USWDS-styled HTML report. The goal of v3 is to replicate the same webform input/output wrapper but swap Promptfoo for **UK AISI Inspect** as the eval engine — and rewrite the whole stack in Python.

**Why Inspect?** Inspect is an open-source Python framework from the UK AI Security Institute with a composable Dataset → Task → Solver → Scorer architecture, 20+ model providers, sandboxed execution, and adoption by major safety labs (Anthropic, DeepMind). It's more research-grade and extensible than Promptfoo, with first-class support for multi-turn, agentic, and safety-focused evaluations.

**Decision:** Full Python rewrite (Flask/FastAPI + Inspect Python API). Same USWDS-styled form as v2, with added Inspect-specific options (solver selection, epochs).

---

## Architecture

```
Google Sheet  →  Evergreen v3 (Flask)  →  Inspect (Python API)  →  LLM Under Test  →  HTML Report
(test cases)     Web App                  eval engine              (OpenAI, etc.)     (3-tab USWDS)
```

### v2 → v3 Module Mapping

| v2 (TypeScript/Promptfoo) | v3 (Python/Inspect) | Purpose |
|---|---|---|
| `src/sheets.ts` | `app/sheets.py` | Fetch Google Sheet CSV → parse rows |
| `src/config.ts` | `app/task_builder.py` | SheetRows → Inspect Task (dataset + solver + scorer) |
| `src/runner.ts` | `app/runner.py` | Execute eval via `inspect_ai.eval()` Python API |
| `src/mapper.ts` | `app/mapper.py` | Inspect EvalLog → report-ready EvalResults |
| `src/types.ts` | `app/types.py` | Shared dataclasses (SheetRow, EvalResults, etc.) |
| `src/report/generator.ts` | `app/report/generator.py` | Render 3-tab HTML report |
| `src/web/server.ts` | `app/server.py` | Flask app: form → pipeline → report |
| `src/web/input.html` | `app/templates/input.html` | USWDS input form (Jinja2) |
| `src/index.ts` | `cli.py` | CLI entry point |

---

## Key Implementation Details

### 1. Sheets Connector (`app/sheets.py`)
Port directly from v2. Fetch public Google Sheet as CSV via `https://docs.google.com/spreadsheets/d/{id}/export?format=csv`, parse into `SheetRow` dataclasses. Same 5-column schema: Question | What to Check | Context | Metric | Severity.

### 2. Task Builder (`app/task_builder.py`) — The Core Translation Layer
This is where the Promptfoo → Inspect translation happens.

**Dataset**: Convert `SheetRow[]` → `inspect_ai.dataset.MemoryDataset` with `Sample` objects:
```python
Sample(
    input=row.question,  # or with context prepended
    target=row.expected_answer,
    metadata={"metric": row.metric, "severity": row.severity, "context": row.context}
)
```

**Scoring strategy — key design change from v2:**

In v2, each test case was scored on *only* its primary metric (the one the SME chose in the sheet). In v3, we score every test case on **all 5 metrics simultaneously** using Inspect's multi-scorer support. The SME-specified metric is still the "primary" for pass/fail readiness, but the other 4 provide supplementary signal.

**Scorer mapping** (replaces v2's `metricToAssertions`):

| Metric | Inspect Scorer | Rubric |
|---|---|---|
| Safety | `model_graded_qa()` | Custom safety rubric (port from v2's `buildSafetyRubric`) |
| Accuracy | `includes()` for keyword tests; `model_graded_fact()` for complex | Uses `target` field directly |
| Ease of Use | `model_graded_qa()` | Custom plain-language rubric (port from v2's `buildEaseOfUseRubric`) |
| Effectiveness | `model_graded_qa()` | Custom effectiveness rubric (port from v2's `buildEffectivenessRubric`) |
| Emotion | `model_graded_qa()` | Custom empathy/tone rubric (port from v2's `buildEmotionRubric`) |

**Multi-scorer implementation**: Use Inspect's list-of-scorers feature:
```python
scorer=[
    safety_scorer(what_to_check),      # model_graded_qa with safety rubric
    accuracy_scorer(what_to_check),    # includes() or model_graded_fact()
    ease_of_use_scorer(what_to_check), # model_graded_qa with ease rubric
    effectiveness_scorer(what_to_check, context),
    emotion_scorer(what_to_check, context),
]
```

**Metrics aggregation**: Use `grouped("severity")` and `grouped("metric")` to auto-generate breakdowns:
```python
metrics=[accuracy(), stderr(), grouped("severity", [accuracy(), stderr()])]
```

**Solver pipeline** (new in v3 — Inspect-specific feature exposed in UI):
- Default: `[generate()]` (simple prompt → response)
- Optional: `[chain_of_thought(), generate()]`
- Optional: `[chain_of_thought(), generate(), self_critique()]`

**System prompt**: Injected via `system_message()` solver prepended to the pipeline.

**Epochs**: Configurable via form (default 1, option for 2-3 for statistical reliability).

### 3. Runner (`app/runner.py`)
Use Inspect's Python API directly (no subprocess):
```python
from inspect_ai import eval

log = eval(
    task,
    model=f"openai/gpt-4o",  # or anthropic/claude-sonnet-4-20250514
    log_dir=tempdir,
)
```

Async execution for the web server (Inspect supports async). Return the `EvalLog` object.

### 4. Mapper (`app/mapper.py`)
Transform Inspect's `EvalLog` → `EvalResults` dataclass for the report.

**Per-sample extraction** (from `log.samples`):
- `sample.scores` → dict of scorer name → `Score` object. Each has `.value` (pass/fail or numeric), `.answer` (extracted answer), `.explanation` (grader reasoning)
- `sample.messages` → full conversation transcript (for Details tab)
- `sample.metadata` → original sheet metadata (metric, severity, context)

**Aggregate extraction** (from `log.results`):
- Overall pass rate + stderr per scorer
- Grouped metrics by severity and by primary metric (from `grouped()`)

**Stats extraction** (from `log.stats`):
- Total input/output tokens, per-sample token counts
- Model name, solver pipeline used, epoch count

### 5. Report Generator (`app/report/generator.py`)

**Redesigned for Inspect** — not a direct port of v2. Same 3 persona tabs, but the content leverages Inspect's richer data model.

#### What Inspect gives us that v2/Promptfoo couldn't

| Inspect Capability | Report Impact |
|---|---|
| **Multiple scorers per sample** | Score every test case on ALL 5 metrics simultaneously, not just the one the SME picked. One question can show safety=PASS, accuracy=FAIL, emotion=PASS. |
| **Score `explanation` field** | Each grader returns detailed reasoning. Surface this in the Details tab — shows *why* something passed or failed, not just that it did. |
| **`grouped()` metrics** | Break down pass rates by severity level, by metric, by context group. Automatic cross-cuts. |
| **`stderr()` / `bootstrap_stderr()`** | Show confidence intervals on pass rates (e.g., "82% ± 6%"). With epochs > 1, this becomes meaningful. |
| **Token usage per sample** | Cost transparency — show total tokens and estimated cost. Useful for procurement. |
| **Solver pipeline transparency** | Show what elicitation strategy was used (standard, CoT, CoT+self-critique). Different strategies may yield different results. |
| **Multi-model eval sets** | Side-by-side model comparison tables when multiple providers are tested. |
| **Message transcript** | Full conversation history per sample — visible in Details tab for debugging. |

#### Tab 1: Summary (Policy / Leadership)

Target: Decision-makers who need a go/no-go signal.

- **Readiness badge**: Ready / Needs Improvement / Not Ready (same logic as v2)
- **Critical failure callout**: Count + list of critical-severity failures with plain-English impact
- **Overall pass rate with confidence**: e.g., "84% ± 4%" (powered by `bootstrap_stderr()`)
- **Metric dimension breakdown**: Bar chart or table showing pass rate per metric (Safety, Accuracy, Ease of Use, Effectiveness, Emotion) — NEW: now every test is scored on all 5 dimensions, not just its primary metric
- **Model comparison summary** (if multi-model): side-by-side pass rates per provider
- **Next steps**: Auto-generated recommendations based on failure patterns
- **Eval metadata**: Date, solver strategy used, epoch count, model(s) tested

#### Tab 2: Analysis (Operations / Program Managers)

Target: People who need to understand *patterns* in failures.

- **Severity × Metric heatmap**: Pass rates broken down by both severity and metric (powered by `grouped()` on metadata keys)
- **Failure pattern analysis**: Cluster failures by metric — e.g., "4 of 5 safety failures are in the tax-deduction context"
- **Per-metric detail cards**: For each of the 5 metrics, show pass rate + stderr, list of failed test cases, and the grader's explanation summary
- **Cost/efficiency panel**: Total tokens used, estimated API cost, tokens per test case (from `log.stats`)
- **Solver impact note**: If CoT or self-critique was used, note this as context for interpreting results

#### Tab 3: Details (Technical / Debugging)

Target: Technical implementers who need to fix failures.

- **Per-test-case expandable rows**: Each row shows question, expected answer, actual response, and a score card across ALL 5 metrics (not just the primary one)
- **Grader explanations**: For each metric score, show the `explanation` field from the Inspect scorer — the full reasoning from the LLM judge
- **Message transcript** (collapsible): Full `messages` array from the Inspect sample — the exact prompts and responses exchanged
- **Extracted answer**: The `answer` field from each scorer, showing what the grader identified as the model's answer
- **Per-sample token usage**: Input/output tokens for each test case
- **Multi-model diff** (if applicable): Side-by-side responses from different providers for the same test case
- **Raw score values**: Numeric scores where applicable (not just pass/fail)

#### Design Constraints (carried from v2)
- Self-contained single-file HTML (no external assets beyond inline USWDS CSS)
- USWDS styling only — no Tailwind, Bootstrap, or custom CSS frameworks
- Plain English — no technical jargon in Summary or Analysis tabs
- Downloadable/shareable as a static file

### 6. Web Server (`app/server.py`)
Flask app with the same route structure as v2:
- `GET /` → USWDS input form
- `POST /api/run` → Start eval job, return `{jobId}`
- `GET /api/status/:jobId` → Poll progress `{step, status, error?}`
- `GET /report/:jobId` → Serve completed HTML report

Same job management: in-memory dict, rate limiting, TTL cleanup.

### 7. Web Form (`app/templates/input.html`)
Same USWDS-styled form as v2, with these additions:
- **Solver strategy dropdown**: "Standard" / "Chain of Thought" / "Chain of Thought + Self-Critique"
- **Epochs field**: Number input (1-3), with hint text explaining statistical reliability
- Keep: evaluation name, Google Sheet URL / preset toggle, provider dropdown, use case selector, progress stepper

### 8. CLI (`cli.py`)
Same commands as v2:
- `evergreen run` — fetch sheet → run evals → generate report
- `evergreen serve` — serve a report file
- `evergreen app` — launch web app

Use `click` or `argparse` for CLI parsing.

---

## Tech Stack

| Layer | v2 | v3 |
|---|---|---|
| Language | TypeScript | Python 3.11+ |
| Web framework | Express | Flask |
| Eval engine | Promptfoo (subprocess) | Inspect (Python API, direct import) |
| CSS framework | USWDS (static files) | USWDS (static files) |
| Templating | Raw HTML string | Jinja2 |
| CLI | Manual argv parsing | click or argparse |
| Package manager | npm | pip / pyproject.toml |

---

## File Structure

```
evergreen-v3/
├── pyproject.toml
├── README.md
├── LICENSE
├── evergreen.yaml              # CLI config file
├── cli.py                      # CLI entry point
├── app/
│   ├── __init__.py
│   ├── server.py               # Flask web app
│   ├── sheets.py               # Google Sheets CSV fetcher
│   ├── task_builder.py         # SheetRow → Inspect Task
│   ├── runner.py               # Execute Inspect eval
│   ├── mapper.py               # EvalLog → EvalResults
│   ├── types.py                # Shared dataclasses
│   ├── report/
│   │   ├── __init__.py
│   │   └── generator.py        # HTML report (3 tabs)
│   ├── templates/
│   │   └── input.html          # USWDS web form (Jinja2)
│   └── static/
│       └── uswds/              # USWDS CSS/JS/fonts
├── presets/                    # Built-in test suites
│   └── ...
└── tests/
    └── test_pipeline.py        # E2E test with mocked data
```

---

## Verification Plan

1. **Unit test** `sheets.py`: parse a sample CSV string → correct SheetRow list
2. **Unit test** `task_builder.py`: SheetRow list → Inspect Task with correct samples, scorers, solver pipeline
3. **Unit test** `mapper.py`: mock EvalLog → correct EvalResults
4. **E2E test** (no API keys): synthetic SheetRows → build task → mock eval output → generate report HTML → verify 3 tabs present
5. **Integration test** (requires API key): run against a real Google Sheet with 3-5 test cases, verify report generates correctly
6. **Web test**: start Flask app, submit form, poll status, verify report served

---

## Implementation Order

1. `app/types.py` — dataclasses
2. `app/sheets.py` — port from v2
3. `app/task_builder.py` — the core Inspect integration
4. `app/runner.py` — eval execution
5. `app/mapper.py` — log → results
6. `app/report/generator.py` — port HTML report
7. `cli.py` — CLI commands
8. `app/server.py` + `app/templates/input.html` — web app
9. `tests/test_pipeline.py` — E2E test
10. Presets — port built-in test suites

---

## Reference

- **Evergreen v2 source**: https://github.com/akschneider1/Evergreen-v2 (cloned at `/tmp/evergreen-v2`)
- **Inspect docs**: https://inspect.aisi.org.uk/
- **Inspect repo**: https://github.com/UKGovernmentBEIS/inspect_ai
- **Inspect key concepts**: Tasks, Solvers, Scorers, Datasets
- **Inspect Python API**: `from inspect_ai import eval, Task, task` / `from inspect_ai.scorer import model_graded_qa, includes` / `from inspect_ai.solver import generate, chain_of_thought, self_critique, system_message`
