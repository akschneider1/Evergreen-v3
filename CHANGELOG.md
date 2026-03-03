# Changelog

All notable changes to Evergreen v3 are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.1.0] — 2026-03-03

### Added

- **Benchmark Catalog** — browse 10 curated, zero-config evaluations covering safety, fairness, accuracy, reasoning, and instruction following. Recommended benchmarks for government use cases pinned at top.
- **Run a benchmark** — select any catalog benchmark, choose an AI model, and run it through a browser form. No coding or command line needed.
- **Real-time progress** — live progress updates while evaluations run, with plain-English step labels.
- **3-tab reports** — every completed run generates a report with a Summary tab (for leadership), Analysis tab (for program managers), and Details tab (for technical staff).
- **Export** — download any report as a self-contained HTML file or PDF.
- **Run history** — all past runs saved for the team with direct links to reports.
- **Team Library** — create custom evaluation benchmarks from your own test cases. Add, review, and approve cases. Publish benchmarks to run alongside built-in ones.
- **CLI** — `evergreen serve`, `evergreen run`, and `evergreen catalog list` commands for terminal users.
- **Initial benchmark set**: TruthfulQA, IFEval, BBQ (Bias), SimpleQA, StrongREJECT, COCONOT, AgentHarm, MMLU, ARC Challenge, BIG-Bench Hard.

### Technical

- FastAPI + Jinja2 + HTMX + Tailwind CSS + DaisyUI
- SQLite database via SQLModel
- Async eval execution via `asyncio.to_thread` wrapping Inspect's Python API
- Data-driven benchmark catalog (YAML files validated against JSON Schema)
- pytest test suite covering catalog, mapper, and all routes (no real API calls in CI)
