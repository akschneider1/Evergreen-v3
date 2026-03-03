# Evergreen v3

**AI evaluation platform for government teams.** A browser-based tool that makes UK AISI's [Inspect](https://inspect.aisi.org.uk/) evaluation framework accessible to non-technical staff — no coding, no command line required.

Run safety and capability benchmarks against any AI tool before you deploy it. Built for state and local government teams working in benefits delivery, public safety, and adjacent domains.

---

## Deploy your own instance

### 1. Fork and open in Replit

1. Fork this repository on GitHub
2. Go to [replit.com](https://replit.com) and click **Import from GitHub**
3. Select your fork — Replit will detect the Python project automatically

### 2. Add your API keys

In the Replit sidebar, open **Secrets** (the lock icon) and add the keys for whichever AI provider(s) you want to test:

| Secret name | Where to get it |
|---|---|
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| `GOOGLE_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

You only need to add keys for the providers you plan to use.

### 3. Click Run

Hit the **Run** button. Replit will install dependencies and start the server. Visit the URL shown in the Replit webview — you'll see the benchmark catalog.

### Environment variables (optional)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./evergreen.db` | Database location |

---

## What you can do

**Browse the benchmark catalog** — 10 curated, zero-config evaluations covering safety, fairness, accuracy, reasoning, and instruction following. Recommended benchmarks for government use cases are pinned at the top.

**Run a benchmark** — select a benchmark, choose an AI model, give your run a name, and click Run. Progress updates in real time. Results are saved automatically.

**View reports** — every completed run generates a 3-tab report:
- **Summary** — plain-English readiness assessment for leadership
- **Analysis** — failure patterns for program managers
- **Details** — full question-by-question results for technical staff

**Export** — download the report as a self-contained HTML file or PDF.

**Team Library** — build custom evaluation benchmarks from your own test cases. Add, review, and approve cases. Publish them to run like any built-in benchmark.

**Run history** — every run is saved for your team. Link directly to any past report.

---

## Contributing

### Architecture

```
Browser (Tailwind + DaisyUI + HTMX)
    ↕ HTMX partial page updates
FastAPI + Jinja2 templates
    ├── Benchmark Catalog  (catalog/benchmarks/*.yaml)
    ├── Run Pipeline       (app/core/runner.py → Inspect → app/core/mapper.py)
    ├── Eval Builder       (app/routes/builder.py)
    └── Run History        (SQLite via SQLModel)
```

### Adding a benchmark

The catalog is data-driven — adding a benchmark means adding one YAML file:

1. Create `catalog/benchmarks/your_benchmark.yaml`
2. Fill in all required fields (see `catalog/schema.yaml` for the full schema)
3. Set `setup_required: false` if it works with just a model API key
4. Set `status: active` to make it visible in the catalog
5. Open a pull request

Example:
```yaml
id: your_benchmark
display_name: "Your Benchmark Name"
description: "One sentence shown on the catalog card (max 160 chars)."
why_it_matters: >
  Plain-language explanation of why this matters for government teams.
  No jargon. Write for a policy officer, not a researcher.
source: inspect_evals
inspect_task: inspect_evals/your_task_name
tags: [safety, accuracy]
use_cases: [benefits_delivery, public_safety, general]
setup_required: false
cost_estimate: low
time_estimate: "5-10 min"
status: active
```

### Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests run fully offline — all external calls (Inspect, LLM APIs) are mocked.

### Development server

```bash
cp .env.example .env
# Add your API keys to .env
uvicorn app.main:app --reload
```

### PR checklist

Every pull request should satisfy the [definition of done](CLAUDE.md#definition-of-done) in `CLAUDE.md`.

---

## License

[MIT](LICENSE)
