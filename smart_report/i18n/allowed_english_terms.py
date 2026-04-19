"""Whitelist of English terms permitted in Russian-language Synthesizer output.

Each set represents a domain category with a clear justification for why the
English form is accepted:
  - No established Russian equivalent exists in practice, OR
  - The term is an international proper name / standard that must not be translated.

When adding a term, put it in the most specific category.
"""

# ---------------------------------------------------------------------------
# Financial terms without a settled Russian substitute
# ---------------------------------------------------------------------------
FINANCIAL: set[str] = {
    "CAPEX",
    "OPEX",
    "NPV",
    "EBITDA",
    "ROI",
    "EBIT",
    "ARR",
    "MRR",
    "LTV",
    "CAC",
    "GBA",
    "NOI",
    "IRR",
    "WACC",
    "FCF",
    "EV",
}

# Case-sensitive financial tokens (must match exactly as written)
FINANCIAL_CASESENSITIVE: set[str] = {
    "P/E",
    "S&P",
}

# ---------------------------------------------------------------------------
# Real-estate / construction certifications
# ---------------------------------------------------------------------------
CERTIFICATIONS: set[str] = {
    "LEED",
    "BREEAM",
    "WELL",
    "DGNB",
    "ESG",
}

# ---------------------------------------------------------------------------
# International brands, consultancies, data providers — proper nouns
# ---------------------------------------------------------------------------
BRAND_NAMES: set[str] = {
    "Knight Frank",
    "Savills",
    "JLL",
    "Colliers",
    "CBRE",
    "PwC",
    "KPMG",
    "EY",
    "BCG",
    "Deloitte",
    "McKinsey",
    "Bloomberg",
    "MSCI",
    "Cushman & Wakefield",
    "NF Group",
    "Nikoliers",
    "IRN",
    "Metrium",
    "bnMAP",
    "Dataflat",
    "Forbes",
    "Reuters",
}

# ---------------------------------------------------------------------------
# Terms established in Russian proptech / real-estate practice
# ---------------------------------------------------------------------------
REAL_ESTATE_ENGLISH: set[str] = {
    "premium",
    "luxury",
    "branded residences",
    "lobby",
    "concierge",
    # Hybrid Cyrillic-Latin forms tolerated as alternatives to pure Russian
    "business-класс",
    "бизнес-класс",
    # "amenities" has entered Russian proptech usage; "аменитис" is a known variant
    "amenities",
    "аменитис",
    "property management",
}

# ---------------------------------------------------------------------------
# Technology abbreviations with no accepted Russian equivalents
# ---------------------------------------------------------------------------
TECH: set[str] = {
    "API",
    "SaaS",
    "CRM",
    "ERP",
    "BIM",
    "IoT",
    "AI",
    "ML",
}

# ---------------------------------------------------------------------------
# Master set — all permitted English tokens
# ---------------------------------------------------------------------------
ALLOWED_ENGLISH: set[str] = (
    FINANCIAL
    | FINANCIAL_CASESENSITIVE
    | CERTIFICATIONS
    | BRAND_NAMES
    | REAL_ESTATE_ENGLISH
    | TECH
)
