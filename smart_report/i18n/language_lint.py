"""Language lint — detects non-whitelisted English tokens in Russian text.

Usage::

    from smart_report.i18n.language_lint import lint_output_language

    warnings = lint_output_language(text)
    for w in warnings:
        print(w.severity, w.token, w.location_context)
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from .allowed_english_terms import ALLOWED_ENGLISH, BRAND_NAMES, FINANCIAL_CASESENSITIVE

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class LanguageWarning(BaseModel):
    """A single instance of a non-whitelisted Latin-script token."""

    token: str
    location_context: str  # ~80-char window around the token (±40 chars each side)
    severity: Literal["warn", "error"]  # "error" when clearly wrong (ALL_CAPS, len>3)


# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# Strip URLs before scanning — they contain valid English path segments
_RE_URL = re.compile(r"https?://\S+")

# Strip code fences (``` ... ```) — we don't lint code blocks
_RE_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)

# Strip inline code (` ... `)
_RE_INLINE_CODE = re.compile(r"`[^`]+`")

# Strip citation references like [REF: ...] or [[N]](url) style links
_RE_REF_BRACKET = re.compile(r"\[(?:REF:|[0-9]+)\][^\]]*")
_RE_MARKDOWN_LINK_TARGET = re.compile(r"\]\(https?://[^)]+\)")

# Strip v4.5 Phase 1 Step 1.1 evidence-grade tags so the lint doesn't
# flag them as anglicisms. Inline tags only ([STRONG] etc.), not the
# claim text following them.
_RE_EVIDENCE_GRADE = re.compile(r"\[(?:STRONG|MODERATE|WEAK|SPECULATIVE)\]")

# Latin-script token extraction
# Matches a token starting with A-Za-z, continuing with word chars or hyphens.
# This intentionally does NOT use \b at the end so that "Outdoor-стек" splits
# at the Cyrillic boundary and yields "Outdoor" as the Latin segment.
_RE_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


# ---------------------------------------------------------------------------
# Multi-word brand normalization helpers
# ---------------------------------------------------------------------------

# Pre-index multi-word brand names for efficient lookup
_MULTI_WORD_BRANDS: list[str] = sorted(
    (b for b in BRAND_NAMES if " " in b or "&" in b),
    key=len,
    reverse=True,  # longest first so greedy matching works
)


def _strip_noise(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Remove URLs, code blocks, inline code, and ref brackets from *text*.

    Returns (cleaned_text, [(start, end), ...]) where the list records the
    byte-offsets of removed spans so we can reconstruct context windows later.
    Replacement is with spaces to preserve character offsets of surviving tokens.
    """
    # Work from largest to smallest range to avoid index drift
    spans_to_remove: list[tuple[int, int]] = []

    def _collect(m: re.Match) -> str:  # type: ignore[type-arg]
        spans_to_remove.append((m.start(), m.end()))
        return " " * (m.end() - m.start())

    result = _RE_CODE_FENCE.sub(_collect, text)
    result = _RE_INLINE_CODE.sub(_collect, result)
    result = _RE_URL.sub(_collect, result)
    result = _RE_MARKDOWN_LINK_TARGET.sub(_collect, result)
    result = _RE_REF_BRACKET.sub(_collect, result)
    result = _RE_EVIDENCE_GRADE.sub(_collect, result)
    return result, spans_to_remove


def _is_whitelisted(token: str) -> bool:
    """Return True if *token* (or a variant of it) is on the whitelist."""
    # Exact match (case-sensitive — important for P/E, S&P, etc.)
    if token in ALLOWED_ENGLISH:
        return True
    if token in FINANCIAL_CASESENSITIVE:
        return True

    # Case-insensitive match for the rest of the whitelist
    token_lower = token.lower()
    for allowed in ALLOWED_ENGLISH:
        if allowed.lower() == token_lower:
            return True

    return False


def _context_window(text: str, match_start: int, match_end: int, width: int = 40) -> str:
    """Extract up to *width* characters on each side of the match."""
    left = max(0, match_start - width)
    right = min(len(text), match_end + width)
    window = text[left:right]
    # Replace newlines for readability in log output
    return window.replace("\n", " ").strip()


def _severity(token: str) -> Literal["warn", "error"]:
    """Classify severity based on the token shape."""
    # ALL-CAPS token longer than 3 chars that is not whitelisted → almost certainly wrong
    if token.isupper() and len(token) > 3:
        return "error"
    return "warn"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def lint_output_language(text: str) -> list[LanguageWarning]:
    """Scan Russian *text* for non-whitelisted Latin-script tokens.

    Algorithm:
    1. Strip URLs, code blocks, inline code, and citation brackets.
    2. Pre-check multi-word brand names (they span multiple tokens) and mask them.
    3. Extract all remaining Latin-script tokens with regex.
    4. For each token, check against ALLOWED_ENGLISH (case-insensitive except
       for case-sensitive items like P/E).
    5. Return a LanguageWarning for each hit.
    """
    if not text:
        return []

    cleaned, _removed = _strip_noise(text)

    # Mask multi-word brand names in one pass so their individual words don't
    # trigger false positives (e.g. "Knight" or "Frank" alone).
    masked = cleaned
    for brand in _MULTI_WORD_BRANDS:
        # Replace the brand with same-length spaces (preserves offsets)
        brand_pattern = re.compile(re.escape(brand), re.IGNORECASE)
        for m in brand_pattern.finditer(masked):
            masked = masked[: m.start()] + " " * len(brand) + masked[m.end() :]

    warnings: list[LanguageWarning] = []

    for m in _RE_LATIN_TOKEN.finditer(masked):
        token = m.group()

        # Strip trailing hyphens that result from hybrid tokens like "Outdoor-стек"
        # where the Cyrillic part ended the regex match boundary.
        token = token.rstrip("-")

        # Skip purely numeric-looking tokens (shouldn't happen given regex, but guard)
        if not token or not any(c.isalpha() for c in token):
            continue

        if _is_whitelisted(token):
            continue

        ctx = _context_window(cleaned, m.start(), m.end())
        warnings.append(
            LanguageWarning(
                token=token,
                location_context=ctx,
                severity=_severity(token),
            )
        )

    return warnings
