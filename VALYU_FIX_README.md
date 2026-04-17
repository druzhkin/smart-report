# Valyu chart_type Literal bug — ready-to-apply fix

Branch: `fix/valyu-chart-type`

## Problem

Valyu SDK (2.9.4) declares `ImageMetadata.chart_type: Optional[Literal["line", "bar", "area"]]`,
but the Valyu API returns `radar`, `pie`, `stackedBar`, `horizontalBar`. Any DeepResearch
status response containing these charts fails pydantic validation, and the whole call
looks like it failed.

Verified with `_probe_valyu_patch.py` — all 4 unknown chart_types rejected before patch,
all pass after.

## What this branch contains

- `valyu_sdk_patch.py` — runtime monkey-patch. Widens `ImageMetadata.chart_type` to
  `Optional[str]`. Idempotent, self-applies on import.

## Activation (one-line edit, NOT on this branch)

In `search_deep.py::valyu_research`, add `import valyu_sdk_patch` right before
`from valyu import Valyu`:

```python
try:
    import valyu_sdk_patch  # noqa: F401  widen chart_type Literal before SDK imports
    from valyu import Valyu  # lazy: `pip install valyu`
except ImportError:
    log.warning("valyu: SDK missing; `pip install valyu`")
    return None
```

That's it. The patch applies on import; Valyu calls that previously died on radar/pie/etc.
now parse cleanly.

Note: `search_deep.py` is currently untracked in git (not committed to main), so the
one-liner is documented here instead of shipped as a diff.

## To apply

```bash
git checkout main
git checkout fix/valyu-chart-type -- valyu_sdk_patch.py
# manually add the import line to search_deep.py::valyu_research
```

## To verify

```bash
python _probe_valyu_patch.py
```

Expected output: all 4 unknown chart_types (`radar`, `horizontalBar`, `stackedBar`,
`pie`) parse successfully after patch.

## Longer-term

When Valyu ships a new SDK with corrected Literal (or Optional[str]), remove the
patch and the import line. Check `valyu.__version__` > 2.9.4 in changelog.
