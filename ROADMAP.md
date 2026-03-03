# Evergreen v3 — Roadmap

Planned enhancements beyond the 0.1.0 and 0.2.0 releases.

---

## Inspect View as the technical persona

**Current state:** The Details tab in every report is a hand-built HTML table — adequate but limited. It shows per-sample pass/fail, the model's response, and scorer explanations, but lacks the depth a technical reviewer needs.

**Goal:** Replace or supersede the Details tab with a full integration of [Inspect View](https://inspect.aisi.org.uk/inspect-view.html) — the rich, interactive log explorer that ships with `inspect-ai`.

Inspect View provides everything a technical reviewer needs: full message transcripts with role-by-role formatting, score breakdowns per scorer, side-by-side model comparison when multiple providers are tested, epoch-level drill-down, and raw metadata. It is purpose-built for the "fix the failures" persona.

**What this requires:**
- Preserve `.eval` log files to a persistent directory (e.g. `logs/{run_id}/`) rather than a temp dir that is cleaned up after each run. The log path should be stored in the `Run` DB record.
- After a run completes, launch `inspect view --log-dir logs/{run_id}` as a subprocess bound to an available port, or serve the log directory via Inspect's Python API.
- In the report, replace (or sit alongside) the Details tab with a link or embedded iframe pointing to the Inspect View instance for that run.
- Alternatively, clone Inspect View's UI components directly into the Jinja2 templates so no subprocess is needed — more self-contained but requires re-implementing their rendering logic.

**User experience:**
- Leadership and program managers: unchanged — Summary and Analysis tabs stay exactly as they are.
- Technical staff: the Details tab becomes a gateway into Inspect View, where they can drill into transcripts, examine every message exchange, and understand exactly why each sample passed or failed.

**Why it matters:** This splits the report cleanly along persona lines. The non-technical view is Evergreen's own; the technical view is Inspect's own, maintained by AISI and continuously improved.

---

## Inspect Scout integration

**What it is:** [Inspect Scout](https://meridianlabs-ai.github.io/inspect_scout/) is a transcript analysis tool from Meridian Labs that scans eval logs for behavioural issues — refusals, evaluation awareness (the model behaving differently because it knows it's being tested), misconfigured environments, inconsistencies, and other red flags.

**Goal:** After every eval run, automatically run Scout scanners over the log and surface findings as a plain-language **"Conversation Health Check"** panel in the report — distinct from the pass/fail scoring, focused on behavioural quality.

**What this adds to each report:**
- A new panel (visible in both Summary and Analysis tabs) showing any Scout findings in plain language: "3 responses showed signs of refusal", "1 response may indicate the AI knew it was being evaluated", "2 responses were inconsistent with earlier answers in the same conversation."
- Threshold badges: green (no issues), amber (minor flags), red (significant concerns).
- In the Details tab (or Inspect View): per-sample Scout annotations alongside the transcript.

**What this requires:**
- Add `inspect-scout` as a dependency.
- After `inspect_eval()` completes and the log is saved, run `scout.scan(log_path)` (or equivalent Scout Python API) in the same background task.
- Map Scout findings to plain-language strings (similar to how we map scorer results in `mapper.py`).
- Add a `scout_findings` field to `ReportData` and render the health check panel in the report templates.

**Why it matters:** Pass/fail scores tell you whether the AI got the right answer. Scout tells you *how* it behaved — which is often more important for a government deployment decision. An AI that passes 90% of questions but shows signs of inconsistency or evaluation-gaming is a different risk than one that fails 30% cleanly.

---

## Other items tracked

- **Multi-model comparison runs** — run the same benchmark against two or three models simultaneously and generate a side-by-side comparison report. Useful for procurement decisions.
- **Additional benchmark sources** — adapters for EleutherAI lm-evaluation-harness and Stanford HELM, expanding the catalog beyond `inspect_evals`.
- **Team benchmark versioning UI** — view diff between benchmark versions, compare results across versions.
- **Scheduled runs** — re-run a saved benchmark on a schedule (e.g. monthly) to track model behaviour over time.
