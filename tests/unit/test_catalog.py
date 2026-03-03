"""Unit tests for app/core/catalog.py"""

import pytest
import yaml
from pathlib import Path

from app.core.catalog import load_catalog, get_benchmark, filter_benchmarks, get_catalog
from app.models import BenchmarkEntry


def test_load_catalog_returns_entries():
    entries = load_catalog()
    assert len(entries) >= 10, "Expected at least 10 benchmark entries"
    assert all(isinstance(e, BenchmarkEntry) for e in entries)


def test_all_entries_are_active():
    entries = load_catalog()
    # All current entries should be active
    assert all(e.status == "active" for e in entries)


def test_all_entries_zero_config():
    entries = load_catalog()
    assert all(not e.setup_required for e in entries)


def test_entries_sorted_by_display_name():
    entries = load_catalog()
    names = [e.display_name for e in entries]
    assert names == sorted(names)


def test_get_benchmark_found():
    entry = get_benchmark("truthfulqa")
    assert entry is not None
    assert entry.id == "truthfulqa"
    assert entry.display_name == "Truthfulness & Hallucination"


def test_get_benchmark_not_found():
    entry = get_benchmark("does_not_exist")
    assert entry is None


def test_filter_by_tag_safety():
    results = filter_benchmarks(tags=["safety"])
    assert len(results) > 0
    assert all("safety" in e.tags for e in results)


def test_filter_by_tag_fairness():
    results = filter_benchmarks(tags=["fairness"])
    assert all("fairness" in e.tags for e in results)


def test_filter_by_use_case():
    results = filter_benchmarks(use_cases=["benefits_delivery"])
    assert len(results) > 0
    assert all("benefits_delivery" in e.use_cases for e in results)


def test_filter_excludes_setup_required(tmp_path, monkeypatch):
    """Entries with setup_required=true should not appear in filter results."""
    from app.core import catalog as cat_mod

    # Inject a fake entry with setup_required=True into the cache
    fake = BenchmarkEntry(
        id="fake_needs_setup",
        display_name="Fake Needs Setup",
        description="X" * 10,
        why_it_matters="test",
        source="inspect_evals",
        inspect_task="inspect_evals/fake",
        tags=["safety"],
        use_cases=["general"],
        setup_required=True,
        cost_estimate="low",
        time_estimate="1 min",
        status="active",
    )
    original = cat_mod._cache[:]
    cat_mod._cache = original + [fake]

    try:
        results = filter_benchmarks(tags=["safety"])
        assert not any(e.id == "fake_needs_setup" for e in results)
    finally:
        cat_mod._cache = original


def test_filter_no_filters_returns_all_active():
    all_active = filter_benchmarks()
    catalog = get_catalog()
    active_zero_config = [e for e in catalog if e.status == "active" and not e.setup_required]
    assert len(all_active) == len(active_zero_config)


def test_invalid_yaml_skipped(tmp_path, monkeypatch):
    """A YAML file that fails schema validation should be skipped, not crash."""
    from app.core import catalog as cat_mod

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("id: bad\ndisplay_name: Bad\n")  # missing required fields

    monkeypatch.setattr(cat_mod, "_CATALOG_DIR", tmp_path)
    monkeypatch.setattr(cat_mod, "_cache", [])

    entries = cat_mod.load_catalog()
    assert entries == []  # bad file skipped, no crash
