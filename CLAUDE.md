# Evergreen v3

Open-source web platform wrapping UK AISI's Inspect eval framework for non-technical state government staff. Browser-based — no CLI, no Python required. Deployed on Replit.

**Users:** Government teams evaluating AI tools pre-deployment (benefits delivery, public safety).
**Eval engine:** `inspect-ai` Python API (direct import, no subprocess).

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (async) |
| Templates | Jinja2 |
| Interactivity | HTMX |
| Styling | Tailwind CSS (CDN) + DaisyUI |
| Database | SQLite + SQLModel |
| Background jobs | FastAPI BackgroundTasks |
| Eval engine | inspect-ai |
| Testing | pytest + httpx |
| CLI | Typer |

Do not add dependencies without a PR comment explaining why existing tools can't solve the problem.

---

## File structure

```
evergreen-v3/
├── app/
│   ├── main.py               # FastAPI app, route registration, lifespan
│   ├── routes/
│   │   ├── benchmarks.py     # Catalog browse, run trigger
│   │   ├── builder.py        # Eval Builder (Team Library)
│   │   ├── runs.py           # Run history, status polling
│   │   └── reports.py        # Report serving, export
│   ├── core/
│   │   ├── catalog.py        # Load + validate benchmark YAML entries
│   │   ├── runner.py         # Execute Inspect eval (async)
│   │   ├── mapper.py         # EvalLog → report-ready results
│   │   └── jobs.py           # Background job state management
│   ├── models.py             # SQLModel DB models
│   ├── templates/            # Jinja2 HTML templates
│   └── static/
├── catalog/
│   ├── schema.yaml           # Benchmark entry schema
│   └── benchmarks/           # One YAML file per benchmark
├── presets/                  # Built-in test case packs
└── tests/
    ├── conftest.py
    ├── unit/
    └── integration/
```

---

## Design principles (apply to every PR)

- **Plain language** — no jargon without an inline explanation; all labels readable by non-technical staff
- **Progressive disclosure** — show the minimum to start; hide advanced options behind "More options"
- **Transparent operations** — show cost + time estimates before runs; real-time progress during runs
- **Accessible** — WCAG AA; keyboard-navigable; helpful (not punishing) validation messages
- **Shareable outputs** — every report has a stable URL; export to PDF/HTML is first-class
- **Minimal visual system** — reuse existing components; three colors max; one typeface

---

## Definition of done

Every PR must satisfy all of the following before merge.

### Design
- [ ] Follows the six design principles above
- [ ] No new jargon without inline plain-language explanation
- [ ] New UI is keyboard-navigable with sufficient color contrast

### Testing
- [ ] Unit tests for any function containing logic
- [ ] Integration test for any new route (happy path + one error case)
- [ ] All external calls mocked — no real API calls in CI
- [ ] `pytest tests/ -v` passes locally

### Documentation
- [ ] Non-trivial functions have a one-sentence docstring
- [ ] `CHANGELOG.md` has an `[Unreleased]` entry in user-facing language
- [ ] `README.md` updated if a new env var, CLI command, or config option was added

---

## Conventions

- All route handlers and core functions are `async def`; blocking calls use `asyncio.to_thread`
- All data shapes use Pydantic models — no raw dicts between layers
- Errors: raise `HTTPException` with a human-readable `detail`; core functions raise typed exceptions; never silently swallow
- Secrets via environment variables only — never in code; document every required env var in README
- One benchmark per YAML file in `catalog/benchmarks/`
