from __future__ import annotations

import json
import re
from pathlib import Path

from backend.v2.models import AuditSummary
from backend.v2.grounding import find_unsupported_precise_numbers


_BANNED_PHRASES = (
    "i appreciate the detailed query",
    "limitations of the search results",
    "limitations of the provided search results",
    "as an ai",
)

_BROKEN_CITATION_PATTERN = re.compile(r"\[(?:\d+(?:\s+from\s+[^\]]+)?)\](?!\()", flags=re.IGNORECASE)
_MOJIBAKE_MARKERS = ("вЂ", "â€", "â†", "â‰")

_RECOMMENDATION_PATTERNS = (
    r"\brecommend",
    r"\bshould\b",
    r"\bpriority\b",
    r"\baction\b",
    r"\bвывод",
    r"\bрекоменд",
)

_REQUIRED_ANALYTICAL_HEADINGS = (
    ("Option Space", "Пространство альтернатив"),
    ("What Could Change The Recommendation", "Что может изменить рекомендацию"),
    ("Unknowns and Next Questions", "Неизвестное и следующие вопросы"),
)


def _section_body(report_md: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+.+$|\Z)",
        report_md,
        flags=re.MULTILINE,
    )
    return match.group(1) if match else ""


def _body_for_grounding_scan(report_md: str) -> str:
    start_match = re.search(r"^##\s+Executive Summary\s*$", report_md, flags=re.MULTILINE)
    if not start_match:
        return report_md
    end_match = re.search(r"^##\s+Evidence Coverage and Source Quality\s*$", report_md, flags=re.MULTILINE)
    if not end_match:
        end_match = re.search(r"^##\s+Sources\s*$", report_md, flags=re.MULTILINE)
    start = start_match.start()
    end = end_match.start() if end_match else len(report_md)
    body = report_md[start:end]
    body = re.sub(r"(?im)^Exhibit\s+\d+.*$", " ", body)
    body = re.sub(r"(?im)^\|.*\|\s*$", " ", body)
    body = re.sub(r"\(\d+\)", " ", body)
    body = re.sub(r"\(Word count:[^)]+\)", " ", body, flags=re.IGNORECASE)
    return body


def audit_report_package(package_dir: str | Path) -> AuditSummary:
    path = Path(package_dir)
    failures: list[str] = []
    warnings: list[str] = []

    required_files = [
        "report.md",
        "report.html",
        "sources.json",
        "claim_table.json",
        "analysis_brief.json",
        "coverage_report.json",
        "quality_assessment.json",
        "quality_iterations.json",
        "adjacent_questions.json",
        "critique_findings.json",
        "decision_triggers.json",
        "lateral_review.json",
    ]
    for filename in required_files:
        if not (path / filename).exists():
            failures.append(f"Missing required artifact: {filename}")

    report_md = (path / "report.md").read_text(encoding="utf-8") if (path / "report.md").exists() else ""
    lowered = report_md.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lowered:
            failures.append(f"Banned meta phrase detected: {phrase}")
    if _BROKEN_CITATION_PATTERN.search(report_md):
        failures.append("Broken footnote-style citations detected; use markdown links or explicit evidence markers")
    if any(marker in report_md for marker in _MOJIBAKE_MARKERS):
        failures.append("Broken text encoding markers detected in report output")

    headings = re.findall(r"^##\s+(.+)$", report_md, flags=re.MULTILINE)
    if len(headings) != len(set(headings)):
        failures.append("Duplicate section headings detected")
    heading_set = {heading.strip() for heading in headings}
    for options in _REQUIRED_ANALYTICAL_HEADINGS:
        if not any(option in heading_set for option in options):
            failures.append(f"Missing analytical section: {' / '.join(options)}")

    paragraphs = [re.sub(r"\s+", " ", chunk).strip().lower() for chunk in report_md.split("\n\n") if len(chunk.strip()) > 40]
    if len(paragraphs) != len(set(paragraphs)):
        warnings.append("Repeated paragraphs detected")

    recommendation_block = _section_body(report_md, "Recommendation and Decision Posture")
    recommendation_lines = [
        line.strip()
        for line in recommendation_block.splitlines()
        if line.strip().startswith("- ")
        and any(re.search(pattern, line.lower()) for pattern in _RECOMMENDATION_PATTERNS)
    ]
    missing_evidence = [
        line
        for line in recommendation_lines
        if "[Evidence:" not in line
        and not re.search(r"\[[^\]]+\]\(https?://[^)]+\)", line)
        and "bounded" not in line.lower()
    ]
    if missing_evidence:
        failures.append("At least one recommendation bullet lacks evidence linkage")

    if (path / "sources.json").exists():
        sources = json.loads((path / "sources.json").read_text(encoding="utf-8"))
        if not sources:
            failures.append("Source pack is empty")
        weak_sources = [source for source in sources if source.get("source_type") == "weak_secondary"]
        if weak_sources:
            failures.append("Weak secondary sources leaked into the final source pack")
        for source in sources:
            if not str(source.get("url", "")).startswith("http"):
                failures.append(f"Invalid source url: {source.get('url', '')}")

    if (path / "claim_table.json").exists():
        claims = json.loads((path / "claim_table.json").read_text(encoding="utf-8"))
        if not claims:
            failures.append("Claim table is empty")
        unsupported_numbers = find_unsupported_precise_numbers(
            _body_for_grounding_scan(report_md),
            [str(item.get("statement", "") or "") for item in claims],
        )
        if unsupported_numbers:
            preview = ", ".join(unsupported_numbers[:4])
            failures.append(f"Unsupported precise numbers detected in report output: {preview}")

    if (path / "coverage_report.json").exists():
        coverage_report = json.loads((path / "coverage_report.json").read_text(encoding="utf-8"))
        coverage_ratio = float(coverage_report.get("coverage_ratio", 0.0) or 0.0)
        contradiction_count = int(coverage_report.get("contradiction_count", 0) or 0)
        if coverage_ratio < 0.99:
            failures.append(f"Core-question coverage is incomplete: {coverage_ratio:.2f}")
        if contradiction_count > 1:
            failures.append(f"Too many unresolved contradiction clusters remain: {contradiction_count}")
        elif contradiction_count == 1:
            warnings.append("One contradiction cluster remains unresolved")

    if (path / "adjacent_questions.json").exists():
        adjacent_questions = json.loads((path / "adjacent_questions.json").read_text(encoding="utf-8"))
        if not adjacent_questions:
            failures.append("Adjacent questions artifact is empty")

    if (path / "critique_findings.json").exists():
        critique_findings = json.loads((path / "critique_findings.json").read_text(encoding="utf-8"))
        if not critique_findings:
            failures.append("Critique findings artifact is empty")

    if (path / "decision_triggers.json").exists():
        decision_triggers = json.loads((path / "decision_triggers.json").read_text(encoding="utf-8"))
        if not decision_triggers:
            failures.append("Decision triggers artifact is empty")

    if (path / "lateral_review.json").exists():
        lateral_review = json.loads((path / "lateral_review.json").read_text(encoding="utf-8"))
        if not lateral_review:
            failures.append("Lateral review artifact is empty")

    if (path / "quality_assessment.json").exists():
        quality_assessment = json.loads((path / "quality_assessment.json").read_text(encoding="utf-8"))
        overall_score = float(quality_assessment.get("overall_score", 0.0) or 0.0)
        verdict = str(quality_assessment.get("verdict", "") or "")
        dimensions = quality_assessment.get("dimensions", []) or []
        topic_alignment = next(
            (
                float(item.get("score", 0.0) or 0.0)
                for item in dimensions
                if str(item.get("dimension", "")) == "topic_alignment"
            ),
            100.0,
        )
        if overall_score < 55.0:
            failures.append(f"Quality score too low for release: {overall_score:.1f}/100")
        if topic_alignment < 70.0:
            failures.append(f"Topic alignment too weak for release: {topic_alignment:.1f}/100")
        elif verdict == "thin":
            warnings.append("Quality verdict is still thin even though the release threshold was met")
        elif overall_score < 65.0:
            warnings.append(f"Quality score is still weak: {overall_score:.1f}/100")
        elif overall_score < 75.0:
            warnings.append(f"Quality score is below target: {overall_score:.1f}/100")

    if (path / "quality_iterations.json").exists():
        quality_iterations = json.loads((path / "quality_iterations.json").read_text(encoding="utf-8"))
        if not quality_iterations:
            failures.append("Quality iterations artifact is empty")
        elif len(quality_iterations) == 1:
            warnings.append("Quality loop did not perform iterative revisions")

    release_status = "released" if not failures else "blocked"
    return AuditSummary(
        release_status=release_status,
        checks_passed=max(0, len(required_files) - len(failures)),
        checks_failed=len(failures),
        failures=failures,
        warnings=warnings,
    )
