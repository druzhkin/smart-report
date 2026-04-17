"""Realistic mocked responses for dry-run mode. NO hardcoded confidence scores."""

from __future__ import annotations

# ---- Mock Matrix (planner output) -----------------------------------------
MOCK_MATRIX = {
    "domains": ["market", "product", "brand"],
    "layers": ["structure", "dynamics", "mechanism"],
    "cells": [
        {
            "id": "market:structure",
            "domain": "market",
            "layer": "structure",
            "scout_task": {
                "cell_id": "market:structure",
                "query": "business-segment Moscow residential developers market share 2024 2025",
                "target_sources": ["Росстат", "ДОМ.РФ", "ЦИАН Аналитика"],
            },
        },
        {
            "id": "product:mechanism",
            "domain": "product",
            "layer": "mechanism",
            "scout_task": {
                "cell_id": "product:mechanism",
                "query": "product differentiation drivers premium developers Moscow cycle time",
                "target_sources": ["НИУ ВШЭ", "Knight Frank", "industry interviews"],
            },
        },
        {
            "id": "brand:dynamics",
            "domain": "brand",
            "layer": "dynamics",
            "scout_task": {
                "cell_id": "brand:dynamics",
                "query": "brand equity developer trust index Moscow longitudinal",
                "target_sources": ["Nielsen", "Ipsos", "Forbes Russia"],
            },
        },
        {
            "id": "market:dynamics",
            "domain": "market",
            "layer": "dynamics",
            "scout_task": {
                "cell_id": "market:dynamics",
                "query": "business-class residential demand elasticity Moscow 2022-2025",
                "target_sources": ["ЦБ РФ", "Росреестр", "Domclick"],
            },
        },
    ],
}

# ---- Mock Findings per scout task ------------------------------------------
MOCK_FINDINGS: dict[str, list[dict]] = {
    "market:structure": [
        {
            "claim": "Top-5 developers held 47% of Moscow business-class launches in 2024.",
            "number": "47%",
            "source_url": "https://www.dom.rf/analytics/2024-business-review/",
            "source_type": "official",
            "verbatim_quote": "Пять крупнейших застройщиков в 2024 году обеспечили 47% новых проектов бизнес-класса.",
        },
        {
            "claim": "Average project scale in business segment grew from 28k m² (2020) to 41k m² (2024).",
            "number": "41000",
            "source_url": "https://cian-analytics.example/moscow-2024/",
            "source_type": "industry",
            "verbatim_quote": None,
        },
    ],
    "product:mechanism": [
        {
            "claim": "Cycle time from permit to sales launch fell 22% for top-quartile developers.",
            "number": "22%",
            "source_url": "https://www.hse.ru/mirror/pubs/share/dev-cycle-2025.pdf",
            "source_type": "academic",
            "verbatim_quote": "Сокращение цикла выхода на продажи составило в среднем 22% для верхнего квартиля девелоперов.",
        },
    ],
    "brand:dynamics": [
        {
            "claim": "Branded launches achieve premium of 8-12% at same location vs. unbranded.",
            "number": "10%",
            "source_url": "https://forbes.ru/realty/brand-premium-2025",
            "source_type": "media",
            "verbatim_quote": None,
        },
    ],
    "market:dynamics": [
        {
            "claim": "Business-class demand elasticity to mortgage rate ≈ -1.3 in 2023-2024.",
            "number": "-1.3",
            "source_url": "https://cbr.ru/analytics/mortgage-elasticity/",
            "source_type": "official",
            "verbatim_quote": "Эластичность спроса в бизнес-классе по ставке составила -1.3 в 2023-2024.",
        },
    ],
}

# ---- Mock Block narrative per cell -----------------------------------------
MOCK_BLOCK: dict[str, dict] = {
    "market:structure": {
        "conclusion": "Business-segment in Moscow is moderately concentrated; top-5 control near-half the flow, but long tail of boutique projects remains viable.",
        "strongest_number": "47%",
        "gap": "No breakdown of concentration by submarket (inside-MKAD vs. New Moscow).",
        "key_assumptions": ["Permit data is a reliable proxy for launched product."],
        "entities": ["ДОМ.РФ", "ПИК", "Донстрой", "MR Group"],
        "variables": ["market_concentration", "average_project_scale"],
    },
    "product:mechanism": {
        "conclusion": "Speed is an operational advantage: cycle-time reduction correlates with capital turnover and brand momentum.",
        "strongest_number": "22%",
        "gap": "Sample size of interviewed developers in HSE study is not disclosed.",
        "key_assumptions": ["Permit-to-launch window is comparable across projects."],
        "entities": ["НИУ ВШЭ"],
        "variables": ["cycle_time", "capital_turnover"],
    },
    "brand:dynamics": {
        "conclusion": "Brand captures an 8-12% price premium at parity-location, indicating trust is priced in.",
        "strongest_number": "10%",
        "gap": "Premium may be confounded with unobserved product quality differences.",
        "key_assumptions": ["Hedonic controls in Forbes methodology are adequate."],
        "entities": ["Forbes"],
        "variables": ["brand_premium", "trust_index"],
    },
    "market:dynamics": {
        "conclusion": "Business-class demand is mortgage-sensitive; a 100bp rate move shifts volume ~13%.",
        "strongest_number": "-1.3",
        "gap": "Elasticity may shift post-2025 if subsidized mortgage programs expire.",
        "key_assumptions": ["Rate pass-through to business-class mortgages is linear."],
        "entities": ["ЦБ РФ"],
        "variables": ["demand_elasticity", "mortgage_rate"],
    },
}

# ---- Mock CrossLinks -------------------------------------------------------
MOCK_CROSS_LINKS = [
    {
        "cell_a": "product:mechanism",
        "cell_b": "brand:dynamics",
        "shared_variable": "capital_turnover",
        "type": "causal_chain",
        "insight": "Faster cycle time frees capital that funds brand investment, which in turn enables price premium — a compounding loop.",
        "evidence_pointers": ["product:mechanism#cycle-time-22%", "brand:dynamics#premium-10%"],
    },
    {
        "cell_a": "market:structure",
        "cell_b": "market:dynamics",
        "shared_variable": "mortgage_rate",
        "type": "shared_mechanism",
        "insight": "Concentration and cyclicality both rise during rate spikes: small players exit first, reinforcing top-5 dominance.",
        "evidence_pointers": ["market:structure#top5-47%", "market:dynamics#elasticity-1.3"],
    },
]
