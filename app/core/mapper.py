"""Maps an Inspect EvalLog to a ReportData object and renders the HTML report."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# ---------------------------------------------------------------------------
# Report data structures
# ---------------------------------------------------------------------------

@dataclass
class SampleResult:
    """Result for a single eval sample (one question/response pair)."""

    index: int
    input: str
    target: str
    output: str
    passed: bool
    scorer_name: str
    explanation: Optional[str]
    tokens_input: int
    tokens_output: int


@dataclass
class ReportData:
    """All data needed to render the 3-tab HTML report."""

    run_id: str
    run_name: str
    benchmark_display_name: str
    model: str
    overall_pass_rate: float
    total_samples: int
    passed_samples: int
    failed_samples: int
    samples: list[SampleResult] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    completed_at: Optional[datetime] = None
    solver_info: str = ""
    error_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------

def map_to_report(log, run) -> ReportData:
    """Convert an Inspect EvalLog + Run into a ReportData object.

    Handles missing or malformed log data gracefully — individual
    sample failures do not crash the whole report.
    """
    from app.core.catalog import get_benchmark

    benchmark = get_benchmark(run.benchmark_id)
    display_name = benchmark.display_name if benchmark else run.benchmark_id

    samples: list[SampleResult] = []
    total_input = 0
    total_output = 0

    for i, sample in enumerate(getattr(log, "samples", []) or []):
        try:
            passed, scorer_name, explanation = _extract_score(sample)
            inp_tok = _safe_int(getattr(getattr(sample, "usage", None), "input_tokens", 0))
            out_tok = _safe_int(getattr(getattr(sample, "usage", None), "output_tokens", 0))
            total_input += inp_tok
            total_output += out_tok

            samples.append(SampleResult(
                index=i + 1,
                input=str(getattr(sample, "input", "") or ""),
                target=str(getattr(sample, "target", "") or ""),
                output=_extract_output(sample),
                passed=passed,
                scorer_name=scorer_name,
                explanation=explanation,
                tokens_input=inp_tok,
                tokens_output=out_tok,
            ))
        except Exception:
            # Never let a single bad sample break the whole report
            continue

    total = len(samples)
    passed_count = sum(1 for s in samples if s.passed)
    pass_rate = (passed_count / total) if total > 0 else 0.0

    return ReportData(
        run_id=run.id,
        run_name=run.name,
        benchmark_display_name=display_name,
        model=run.model,
        overall_pass_rate=pass_rate,
        total_samples=total,
        passed_samples=passed_count,
        failed_samples=total - passed_count,
        samples=samples,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        completed_at=getattr(run, "completed_at", None),
    )


def _extract_score(sample) -> tuple[bool, str, Optional[str]]:
    """Extract pass/fail, scorer name, and explanation from a sample."""
    scores = getattr(sample, "scores", None) or {}
    if not scores:
        return False, "unknown", None

    # Use the first scorer if multiple exist
    scorer_name = next(iter(scores))
    score_obj = scores[scorer_name]

    value = getattr(score_obj, "value", None)
    explanation = getattr(score_obj, "explanation", None)

    # Inspect scores: "C" = correct, "I" = incorrect, or numeric 1.0/0.0
    if isinstance(value, str):
        passed = value.upper() in ("C", "CORRECT", "PASS", "TRUE", "P", "1")
    elif isinstance(value, (int, float)):
        passed = float(value) >= 0.5
    else:
        passed = False

    return passed, scorer_name, explanation


def _extract_output(sample) -> str:
    """Extract the model's final text response from a sample."""
    # Try the output field first
    output = getattr(sample, "output", None)
    if output:
        if hasattr(output, "completion"):
            return str(output.completion or "")
        if hasattr(output, "choices"):
            choices = output.choices or []
            if choices:
                return str(getattr(getattr(choices[0], "message", None), "content", "") or "")
    # Fall back to last assistant message
    messages = getattr(sample, "messages", []) or []
    for msg in reversed(messages):
        if getattr(msg, "role", None) == "assistant":
            return str(getattr(msg, "content", "") or "")
    return ""


def _safe_int(val) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Report renderer
# ---------------------------------------------------------------------------

def render_report(data: ReportData) -> str:
    """Render a self-contained HTML report string with 3 DaisyUI tabs."""

    pass_pct = round(data.overall_pass_rate * 100)
    readiness = _readiness_label(pass_pct, data.failed_samples, data.samples)
    readiness_color = {"Ready": "success", "Needs Improvement": "warning", "Not Ready": "error"}[readiness]

    failed_samples = [s for s in data.samples if not s.passed]
    passed_samples = [s for s in data.samples if s.passed]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(data.run_name)} — Evergreen Report</title>
<link href="https://cdn.jsdelivr.net/npm/daisyui@4/dist/full.min.css" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-base-200 min-h-screen">

<!-- Nav bar -->
<div class="navbar bg-base-100 shadow-sm px-4 mb-6">
  <div class="navbar-start">
    <a href="/" class="text-xl font-bold text-primary">🌲 Evergreen</a>
    <span class="ml-2 badge badge-ghost badge-sm">v3</span>
  </div>
  <div class="navbar-center hidden md:flex gap-2">
    <a href="/" class="btn btn-ghost btn-sm">Benchmark Catalog</a>
    <a href="/history" class="btn btn-ghost btn-sm">Run History</a>
    <a href="/library" class="btn btn-ghost btn-sm">Team Library</a>
  </div>
  <div class="navbar-end gap-2">
    <a href="/run/{data.run_id}/export/html" class="btn btn-outline btn-sm">Download HTML</a>
    <a href="/run/{data.run_id}/export/pdf" class="btn btn-outline btn-sm">Download PDF</a>
  </div>
</div>

<div class="max-w-5xl mx-auto px-4 pb-8">

  <div class="mb-6">
    <a href="/history" class="text-sm text-base-content/50 hover:text-base-content">← Run History</a>
    <h1 class="text-3xl font-bold mt-1">{_esc(data.run_name)}</h1>
    <p class="text-base-content/60 mt-1">
      {_esc(data.benchmark_display_name)} &middot; {_esc(data.model)}
      {f'&middot; {data.completed_at.strftime("%b %d, %Y %H:%M UTC")}' if data.completed_at else ''}
    </p>
  </div>

  <div role="tablist" class="tabs tabs-lifted tabs-lg">

    <!-- TAB 1: SUMMARY -->
    <input type="radio" name="report_tabs" role="tab" class="tab" aria-label="Summary" checked>
    <div role="tabpanel" class="tab-content bg-base-100 border-base-300 rounded-box p-6">
      <h2 class="text-xl font-semibold mb-4">Summary</h2>

      <div class="stats shadow mb-6 w-full">
        <div class="stat">
          <div class="stat-title">Readiness</div>
          <div class="stat-value text-{readiness_color}">{readiness}</div>
          <div class="stat-desc">Based on overall results</div>
        </div>
        <div class="stat">
          <div class="stat-title">Pass Rate</div>
          <div class="stat-value">{pass_pct}%</div>
          <div class="stat-desc">{data.passed_samples} of {data.total_samples} questions passed</div>
        </div>
        <div class="stat">
          <div class="stat-title">Questions Tested</div>
          <div class="stat-value">{data.total_samples}</div>
          <div class="stat-desc">{data.failed_samples} failed</div>
        </div>
      </div>

      {_readiness_callout(readiness, readiness_color, failed_samples)}

      <div class="mt-4 text-sm text-base-content/50">
        Tokens used: {data.total_input_tokens:,} input / {data.total_output_tokens:,} output
      </div>
    </div>

    <!-- TAB 2: ANALYSIS -->
    <input type="radio" name="report_tabs" role="tab" class="tab" aria-label="Analysis">
    <div role="tabpanel" class="tab-content bg-base-100 border-base-300 rounded-box p-6">
      <h2 class="text-xl font-semibold mb-4">Analysis</h2>

      {"<p class='text-success'>All questions passed — no failures to analyze.</p>" if not failed_samples else ""}

      {_failure_list(failed_samples)}
    </div>

    <!-- TAB 3: DETAILS -->
    <input type="radio" name="report_tabs" role="tab" class="tab" aria-label="Details (Technical)">
    <div role="tabpanel" class="tab-content bg-base-100 border-base-300 rounded-box p-6">
      <h2 class="text-xl font-semibold mb-2">Details <span class="badge badge-neutral badge-sm align-middle">For technical staff</span></h2>
      <p class="text-sm text-base-content/60 mb-4">Full question-by-question results including model responses and scoring rationale.</p>
      <div class="overflow-x-auto">
        <table class="table table-zebra table-sm w-full">
          <thead>
            <tr><th>#</th><th>Question</th><th>Result</th><th>Response</th><th>Explanation</th></tr>
          </thead>
          <tbody>
            {''.join(_sample_row(s) for s in data.samples)}
          </tbody>
        </table>
      </div>
    </div>

  </div><!-- end tabs -->
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def _readiness_label(pass_pct: int, failed: int, samples: list[SampleResult]) -> str:
    if pass_pct >= 80 and failed == 0:
        return "Ready"
    if pass_pct >= 60:
        return "Needs Improvement"
    return "Not Ready"


def _readiness_callout(readiness: str, color: str, failed: list[SampleResult]) -> str:
    if readiness == "Ready":
        return f'<div class="alert alert-success"><span>All checks passed. This AI performed well on this evaluation.</span></div>'
    if not failed:
        return ""
    items = "".join(f"<li>{_esc(s.input[:120])}{'...' if len(s.input) > 120 else ''}</li>" for s in failed[:5])
    more = f"<li>...and {len(failed) - 5} more</li>" if len(failed) > 5 else ""
    return f"""<div class="alert alert-{color}">
  <div>
    <p class="font-semibold">{len(failed)} question{"s" if len(failed) != 1 else ""} failed this evaluation:</p>
    <ul class="list-disc list-inside mt-2 text-sm">{items}{more}</ul>
  </div>
</div>"""


def _failure_list(failed: list[SampleResult]) -> str:
    if not failed:
        return ""
    rows = ""
    for s in failed:
        rows += f"""
<div class="collapse collapse-arrow bg-base-200 mb-2">
  <input type="checkbox">
  <div class="collapse-title font-medium text-sm">
    Q{s.index}: {_esc(s.input[:100])}{'...' if len(s.input) > 100 else ''}
  </div>
  <div class="collapse-content text-sm">
    <p><span class="font-semibold">Expected:</span> {_esc(s.target)}</p>
    <p class="mt-1"><span class="font-semibold">AI responded:</span> {_esc(s.output[:400])}{'...' if len(s.output) > 400 else ''}</p>
    {f'<p class="mt-1 text-base-content/60"><span class="font-semibold">Scorer note:</span> {_esc(s.explanation)}</p>' if s.explanation else ''}
  </div>
</div>"""
    return rows


def _sample_row(s: SampleResult) -> str:
    badge = '<span class="badge badge-success badge-sm">Pass</span>' if s.passed else '<span class="badge badge-error badge-sm">Fail</span>'
    return f"""<tr>
  <td>{s.index}</td>
  <td class="max-w-xs truncate" title="{_esc(s.input)}">{_esc(s.input[:80])}</td>
  <td>{badge}</td>
  <td class="max-w-xs truncate" title="{_esc(s.output)}">{_esc(s.output[:80])}</td>
  <td class="max-w-xs truncate text-xs text-base-content/60" title="{_esc(s.explanation or '')}">{_esc((s.explanation or '')[:80])}</td>
</tr>"""


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
