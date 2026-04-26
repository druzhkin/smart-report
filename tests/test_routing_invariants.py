"""v3 brief §3.5 — non-negotiable architectural invariants.

These tests guard the Valyu-first architecture. They cannot be skipped,
deleted, or modified to pass. Any PR that does so is invalid per the
brief's rule:

> Этот тест нельзя skip'нуть, удалить или модифицировать. Любой PR,
> делающий это — invalid.

If the invariant is genuinely wrong, the right path is a brief revision
(WEEK_BRIEF_v4 etc.) explicitly relaxing the invariant and updating
this test in the same PR with a clear justification.
"""

from __future__ import annotations

import pytest

from smart_report.sources.routing_matrix import (
    ROUTING_MATRIX,
    VALYU,
    VALYU_COVERED_DOMAINS,
)


def test_valyu_is_primary_for_covered_domains():
    """Valyu MUST be primary on every domain in VALYU_COVERED_DOMAINS.

    Per v3 brief §0 + §3.5 this is the architectural invariant for the
    entire Valyu-first design. Augment backends (Tavily/Exa) only run
    when Valyu returns empty/error — they NEVER replace Valyu as primary.
    """
    for domain in VALYU_COVERED_DOMAINS:
        primary, _augment = ROUTING_MATRIX[domain]
        assert primary == VALYU, (
            f"Valyu MUST be primary for {domain}. "
            f"Got primary={primary!r} instead. "
            f"This invariant is non-negotiable per WEEK_BRIEF_v3 §3.5."
        )


def test_routing_matrix_covers_every_invariant_domain():
    """If someone adds to VALYU_COVERED_DOMAINS without updating
    ROUTING_MATRIX, fail loudly rather than KeyError at runtime."""
    for domain in VALYU_COVERED_DOMAINS:
        assert domain in ROUTING_MATRIX, (
            f"VALYU_COVERED_DOMAINS lists {domain!r} but ROUTING_MATRIX "
            f"has no entry for it — invariant cannot be enforced."
        )


def test_no_covered_domain_has_valyu_as_augment_only():
    """Defensive: catches the failure mode where someone makes Valyu the
    AUGMENT instead of primary on a covered domain (which would mean
    Valyu only runs when the *other* backend fails — exact opposite of
    the invariant)."""
    for domain in VALYU_COVERED_DOMAINS:
        primary, augment = ROUTING_MATRIX[domain]
        if augment == VALYU:
            pytest.fail(
                f"{domain}: Valyu is registered as augment, not primary. "
                f"The invariant requires Valyu primary on covered domains. "
                f"primary={primary!r}, augment={augment!r}."
            )


def test_uncovered_domains_do_not_make_valyu_primary():
    """Mirror image: domains NOT in VALYU_COVERED_DOMAINS should not
    accidentally use Valyu as primary either — those routes were
    chosen by the brief because Valyu is structurally weak there
    (russian_market, realtime_news, general). If someone makes Valyu
    primary on, say, russian_market, they're burning Valyu calls on a
    domain the Day 1 capability map shows it cannot serve."""
    for domain, (primary, _augment) in ROUTING_MATRIX.items():
        if domain not in VALYU_COVERED_DOMAINS:
            assert primary != VALYU, (
                f"{domain} is NOT in VALYU_COVERED_DOMAINS but ROUTING_MATRIX "
                f"sets Valyu as primary. Either add {domain!r} to "
                f"VALYU_COVERED_DOMAINS (if Valyu actually covers it) or fix "
                f"the matrix to use a domain-appropriate primary."
            )
