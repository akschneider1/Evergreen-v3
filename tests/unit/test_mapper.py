"""Unit tests for app/core/mapper.py"""

from types import SimpleNamespace
from datetime import datetime

import pytest

from app.core.mapper import map_to_report, render_report, _extract_score, _extract_output
from app.models import Run


def _make_run(**kwargs):
    defaults = dict(
        id="test-run-id",
        name="Test Run",
        benchmark_id="truthfulqa",
        model="gpt-4o",
        status="complete",
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        pass_rate=None,
        error=None,
        report_html=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_score(value, explanation=None):
    return SimpleNamespace(value=value, explanation=explanation)


def _make_sample(input_text="Q?", target="A", output_text="A", score_value="C", explanation="looks good"):
    return SimpleNamespace(
        input=input_text,
        target=target,
        output=SimpleNamespace(completion=output_text),
        scores={"model_graded_qa": _make_score(score_value, explanation)},
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        messages=[],
    )


def _make_log(samples):
    return SimpleNamespace(samples=samples)


# ---------------------------------------------------------------------------

def test_map_to_report_pass_rate():
    samples = [_make_sample(score_value="C")] * 3 + [_make_sample(score_value="I")]
    log = _make_log(samples)
    run = _make_run()
    data = map_to_report(log, run)
    assert data.total_samples == 4
    assert data.passed_samples == 3
    assert data.failed_samples == 1
    assert round(data.overall_pass_rate, 2) == 0.75


def test_map_to_report_all_pass():
    samples = [_make_sample(score_value="C")] * 5
    data = map_to_report(_make_log(samples), _make_run())
    assert data.overall_pass_rate == 1.0
    assert data.failed_samples == 0


def test_map_to_report_all_fail():
    samples = [_make_sample(score_value="I")] * 3
    data = map_to_report(_make_log(samples), _make_run())
    assert data.overall_pass_rate == 0.0
    assert data.passed_samples == 0


def test_map_to_report_empty_samples():
    data = map_to_report(_make_log([]), _make_run())
    assert data.overall_pass_rate == 0.0
    assert data.total_samples == 0


def test_map_to_report_token_totals():
    samples = [_make_sample()] * 4  # each has 10 input + 20 output tokens
    data = map_to_report(_make_log(samples), _make_run())
    assert data.total_input_tokens == 40
    assert data.total_output_tokens == 80


def test_failed_samples_have_correct_fields():
    samples = [_make_sample(score_value="I", input_text="Test Q", explanation="Wrong answer")]
    data = map_to_report(_make_log(samples), _make_run())
    assert data.failed_samples == 1
    assert data.samples[0].passed is False
    assert data.samples[0].explanation == "Wrong answer"


def test_missing_scorer_does_not_crash():
    """A sample with no scores should be treated as failed, not raise an exception."""
    bad_sample = SimpleNamespace(
        input="Q?", target="A",
        output=SimpleNamespace(completion="A"),
        scores={},  # empty — no scorer
        usage=SimpleNamespace(input_tokens=5, output_tokens=5),
        messages=[],
    )
    data = map_to_report(_make_log([bad_sample]), _make_run())
    assert data.total_samples == 1
    assert data.passed_samples == 0


def test_malformed_sample_skipped():
    """A sample that raises an exception during extraction should be skipped."""
    broken = SimpleNamespace()  # missing all attributes
    good = _make_sample(score_value="C")
    data = map_to_report(_make_log([broken, good]), _make_run())
    # broken skipped, good included
    assert data.total_samples == 1
    assert data.passed_samples == 1


def test_render_report_contains_three_tabs():
    samples = [_make_sample(score_value="C")] * 2
    data = map_to_report(_make_log(samples), _make_run())
    html = render_report(data)
    assert "Summary" in html
    assert "Analysis" in html
    assert "Details" in html


def test_render_report_readiness_ready():
    samples = [_make_sample(score_value="C")] * 5
    data = map_to_report(_make_log(samples), _make_run())
    html = render_report(data)
    assert "Ready" in html


def test_render_report_readiness_not_ready():
    samples = [_make_sample(score_value="I")] * 5
    data = map_to_report(_make_log(samples), _make_run())
    html = render_report(data)
    assert "Not Ready" in html


def test_extract_score_correct_values():
    for val in ("C", "CORRECT", "PASS", "P", "1"):
        score = SimpleNamespace(value=val, explanation=None)
        passed, _, _ = _extract_score(SimpleNamespace(scores={"s": score}))
        assert passed is True, f"Expected True for value={val!r}"

    for val in ("I", "INCORRECT", "FAIL", "0"):
        score = SimpleNamespace(value=val, explanation=None)
        passed, _, _ = _extract_score(SimpleNamespace(scores={"s": score}))
        assert passed is False, f"Expected False for value={val!r}"


def test_extract_score_numeric():
    score_pass = SimpleNamespace(value=1.0, explanation=None)
    score_fail = SimpleNamespace(value=0.0, explanation=None)
    assert _extract_score(SimpleNamespace(scores={"s": score_pass}))[0] is True
    assert _extract_score(SimpleNamespace(scores={"s": score_fail}))[0] is False
