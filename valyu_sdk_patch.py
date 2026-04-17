"""Runtime patch for Valyu SDK chart_type Literal bug.

Problem
-------
Valyu SDK (2.9.x) declares:

    class ImageMetadata(BaseModel):
        chart_type: Optional[Literal["line", "bar", "area"]] = None

but the Valyu API returns additional chart types that the SDK doesn't know
about: ``radar``, ``pie``, ``stackedBar``, ``horizontalBar``, and likely
more. Any DeepResearch status response containing such an image fails
pydantic validation with ``literal_error`` — so the whole call looks like
it failed, even though the underlying research completed successfully.

This was observed during the 2026-04-17 A/B corpus-flow runs:
  - Q1 legacy: 5/11 Valyu calls failed via this bug (55% success)
  - Q1 corpus: 1/4 Valyu calls failed via this bug (25% success)

Fix
---
Widen the ``chart_type`` field annotation to ``Optional[str]`` at import
time. We lose nothing — the field is only used for the SDK consumer's
awareness, not for business logic. Any future chart type Valyu adds will
pass through instead of killing the call.

Usage
-----
Import this module BEFORE any code that calls ``valyu.Valyu(...).deepresearch.*``:

    import valyu_sdk_patch  # noqa: F401  — applies monkey-patch on import
    from valyu import Valyu

The patch is idempotent (safe to import multiple times).
"""
from __future__ import annotations

import logging
import typing

log = logging.getLogger(__name__)

_APPLIED = False


def _apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    try:
        from valyu.types.deepresearch import ImageMetadata
        from pydantic.fields import FieldInfo
    except ImportError:
        log.debug("valyu_sdk_patch: valyu SDK not importable, skipping")
        return

    ImageMetadata.model_fields["chart_type"] = FieldInfo(
        annotation=typing.Optional[str],
        default=None,
    )
    ImageMetadata.model_rebuild(force=True)
    _APPLIED = True
    log.info("valyu_sdk_patch: widened ImageMetadata.chart_type to Optional[str]")


_apply()
