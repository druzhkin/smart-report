"""smart_report.i18n — internationalisation utilities.

Public API::

    from smart_report.i18n import lint_output_language, LanguageWarning
    from smart_report.i18n import ALLOWED_ENGLISH
"""

from .allowed_english_terms import ALLOWED_ENGLISH  # noqa: F401
from .language_lint import LanguageWarning, lint_output_language  # noqa: F401

__all__ = [
    "ALLOWED_ENGLISH",
    "LanguageWarning",
    "lint_output_language",
]
