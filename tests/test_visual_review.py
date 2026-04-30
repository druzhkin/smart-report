from __future__ import annotations

from smart_report.visual_review import build_visual_review_gate


def test_visual_review_pending_when_render_passed_but_not_approved():
    review = build_visual_review_gate(
        {"status": "passed", "render_index": "tmp/artifact/index.html"},
        approved=False,
    )

    assert review.ready is False
    assert review.status == "pending"
    assert review.render_index.endswith("index.html")
    assert len(review.items) >= 6
    assert all(item.status == "pending" for item in review.items)


def test_visual_review_approved_when_reviewer_approves():
    review = build_visual_review_gate(
        {"status": "passed", "render_index": "tmp/artifact/index.html"},
        approved=True,
        reviewer_notes={"tables": "Tables checked manually."},
    )

    assert review.ready is True
    assert review.status == "approved"
    assert any(item.id == "tables" and item.notes for item in review.items)


def test_visual_review_blocked_when_render_qa_not_passed():
    review = build_visual_review_gate({"status": "blocked"})

    assert review.ready is False
    assert review.status == "blocked"
    assert all(item.status == "blocked" for item in review.items)
