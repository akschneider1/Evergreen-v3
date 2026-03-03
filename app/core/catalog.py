"""Benchmark catalog loader — reads and validates YAML entries from catalog/benchmarks/."""

from pathlib import Path
from typing import Optional
import yaml
import jsonschema

from app.models import BenchmarkEntry

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_CATALOG_DIR = Path(__file__).parent.parent.parent / "catalog" / "benchmarks"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "catalog" / "schema.yaml"

# ---------------------------------------------------------------------------
# Module-level cache (populated once at app startup via load_catalog())
# ---------------------------------------------------------------------------

_cache: list[BenchmarkEntry] = []
_index: dict[str, BenchmarkEntry] = {}  # id → entry for O(1) lookups


def load_catalog() -> list[BenchmarkEntry]:
    """Load all benchmark YAML files, validate against schema, and cache.

    Returns the list of valid BenchmarkEntry objects sorted by display_name.
    Invalid files are skipped with a warning rather than crashing the app.
    """
    global _cache, _index

    schema = yaml.safe_load(_SCHEMA_PATH.read_text())
    entries: list[BenchmarkEntry] = []

    for path in sorted(_CATALOG_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        try:
            jsonschema.validate(instance=raw, schema=schema)
        except jsonschema.ValidationError as exc:
            print(f"[catalog] Skipping {path.name}: {exc.message}")
            continue
        entries.append(BenchmarkEntry(**raw))

    _cache = sorted(entries, key=lambda e: e.display_name)
    _index = {e.id: e for e in _cache}
    return _cache


def get_catalog() -> list[BenchmarkEntry]:
    """Return the cached catalog, loading it first if empty."""
    if not _cache:
        load_catalog()
    return _cache


def get_benchmark(benchmark_id: str) -> Optional[BenchmarkEntry]:
    """Look up a single benchmark by id. O(1) via dict index."""
    if not _index:
        load_catalog()
    return _index.get(benchmark_id)


def filter_benchmarks(
    tags: Optional[list[str]] = None,
    use_cases: Optional[list[str]] = None,
    status: str = "active",
) -> list[BenchmarkEntry]:
    """Return benchmarks matching the given filters.

    Only returns entries with setup_required=False and the given status.
    If tags or use_cases are provided, the entry must match at least one value
    from each supplied list.
    """
    results = [e for e in get_catalog() if e.status == status and not e.setup_required]

    if tags:
        results = [e for e in results if any(t in e.tags for t in tags)]
    if use_cases:
        results = [e for e in results if any(u in e.use_cases for u in use_cases)]

    return results
