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

## Eval Builder — self-service and moderated session modes

**Current state:** The Eval Builder is a team-internal tool. Staff create test cases, approve them, and publish benchmarks for the team to run.

**Goal:** Extend the Eval Builder into three distinct participation modes, inspired by Karya's moderated data collection workflows and weval's structured eval spec format.

### Mode 1 — Self-service public contribution

A simplified, public-facing form where frontline staff or members of the public can submit test cases without logging in or understanding the underlying evaluation framework. Submissions enter a moderation queue and require approval before joining a benchmark.

This is the equivalent of a suggestion box attached directly to the evaluation pipeline. The people who know what the AI gets wrong are often the people using it — caseworkers, constituents, call centre staff. This mode lets them contribute that knowledge in a structured way.

**What this requires:**
- A public-facing `/contribute` route with a minimal form: "What would you ask this AI?" and "What should it say?" — no metric or severity fields visible.
- Submissions land in a `pending` state in the existing `EvalCase` model; the review queue in the Team Library handles approval.
- Optional: a submission token or session ID so contributors can see whether their cases were approved without requiring an account.

### Mode 2 — Moderated user research session

A facilitator creates a named **Session** — a time-bounded, structured collection activity. Participants join via a link and contribute test cases as part of a guided workshop or research interview. The session captures participant context alongside each submission (role, service area, scenario type).

This is a digital participatory design session. The goal is not just to collect test cases but to understand what scenarios people care about, what language they use, and what failure modes they anticipate — insight that shapes the whole evaluation strategy, not just the test case library.

**What this requires:**
- A `Session` model: id, name, facilitator, description, status (open/closed), created_at.
- Participants join via a session link and optionally provide context (role, department) before contributing.
- Facilitator view: live dashboard of contributions as they come in, ability to flag or approve cases in real time during the session.
- Session export: download all contributions as CSV for analysis, or import approved cases directly into a Team Benchmark.
- Session analytics: word frequency in questions submitted, distribution of scenario types, most common concerns.

### Mode 3 — Usability testing observation capture

A facilitator and participant interact with the AI tool being evaluated. The facilitator (or participant) captures observations as structured test cases mid-session — "the AI did X when we expected Y." These observations become test cases in the Team Library.

The distinction from Mode 2: the subject is the AI's *usability* rather than its safety or accuracy. Test cases here may be about confusing responses, unhelpful tone, or task failures — not just wrong answers. This mode bridges AI evaluation and traditional UX research.

**What this requires:**
- A "capture" mode within the Eval Builder: a floating form that lets a facilitator quickly log an observation during a live session without leaving the current page.
- Observations are linked to a named usability session for grouping and export.
- An optional severity field pre-set to "usability" as a distinct metric category.

**Why it matters across all three modes:** The people best positioned to identify AI failure modes are often those closest to the service — not the technical team that built the AI. These modes create a systematic pipeline from lived experience to structured evaluation, closing the loop between user research and AI safety testing.

---

## 80/20 evaluation framework — automated benchmarks + human red teaming

**The principle:** Automated benchmarks reliably cover known failure modes at scale. Human red teaming finds novel, adversarial, and edge-case failures that no automated benchmark anticipates. The right balance for pre-deployment evaluation is roughly 80% automated, 20% structured human red teaming.

**Current state:** Evergreen handles the 80% — automated benchmark runs against a model. The 20% has no structured support yet.

**Goal:** Make human red teaming a first-class concept in Evergreen, with the platform actively supporting the handoff between automated and human testing and closing the loop so red team findings feed back into future automated runs.

### Platform support for the 80%

Automated runs already work. What's missing is guidance on *coverage*:
- After a benchmark run, surface a **coverage view**: which risk categories (safety, fairness, accuracy, instruction following, tone) are well-covered by existing automated tests, and which have gaps?
- Flag categories where the automated pass rate is high but sample count is low — passing 3 out of 3 safety questions is not the same as passing 60 out of 60.
- Use Scout findings (see Inspect Scout integration) to identify behavioural areas that passed the automated scorer but showed anomalies — prime candidates for red team attention.

### Structured red team sessions (the 20%)

Red teaming is not ad hoc probing — it is a structured adversarial activity. The platform should guide it:
- A **Red Team Session** is a first-class session type in the Eval Builder, distinct from a user research session. It is explicitly adversarial in framing.
- Guided prompt templates by risk category: "What could go wrong if a user tried to misuse this AI for X?", "What happens if a user provides false context?", "Can you get the AI to contradict itself?", "What does the AI do when asked something outside its intended scope?"
- Role-based templates: red teamers can adopt adversarial personas (frustrated constituent, bad-faith actor, confused elderly user, non-native speaker) to surface failure modes that neutral testing misses.
- Session outputs land in the Team Library as approved test cases, tagged `source: red_team`.

### Closing the loop

The most important part: red team findings should not stay in a report. They should become automated tests.
- After a red team session, the facilitator reviews findings and marks any as "promote to automated test."
- Promoted findings are added to the relevant Team Benchmark as approved cases.
- The next automated run will include them — turning a one-time human discovery into a permanent regression check.
- Over time, the automated test suite grows to cover the attack surface that red teamers mapped.

**Why the 80/20 split matters for government:** Automated benchmarks answer "does this AI meet the standard?" Red teaming answers "what does this AI do when someone tries to break it?" Both questions must be answered before deployment — especially for public-facing services where adversarial use is not hypothetical.

---

## Other items tracked

- **Multi-model comparison runs** — run the same benchmark against two or three models simultaneously and generate a side-by-side comparison report. Useful for procurement decisions.
- **Additional benchmark sources** — adapters for EleutherAI lm-evaluation-harness and Stanford HELM, expanding the catalog beyond `inspect_evals`.
- **Team benchmark versioning UI** — view diff between benchmark versions, compare results across versions.
- **Scheduled runs** — re-run a saved benchmark on a schedule (e.g. monthly) to track model behaviour over time.
