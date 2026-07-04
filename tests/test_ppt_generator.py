import io

from pptx import Presentation

SAMPLE_STATS = {
    "total_issues": 12,
    "committed_points": 53.0,
    "completed_points": 8.0,
    "status_counts": {"In Progress": 6, "To Do": 4, "In Review": 1, "Done": 1},
    "by_assignee": {"Alice Smith": {"total": 4, "done": 1}},
    "carryover_keys": ["ENG-1", "ENG-2", "ENG-3"],
    "blocked_issues": [{"key": "ENG-5", "summary": "DB migration", "blocker_count": 1}],
}

SAMPLE_NARRATIVE = {
    "highlights": ["Shipped SSO integration"],
    "risks": ["DB migration blocked on DBA approval"],
    "next_steps": ["Unblock ENG-9 with DBA"],
}


def _all_text(slide) -> str:
    chunks = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            chunks.append(shape.text_frame.text)
    return "\n".join(chunks)


def test_build_produces_five_slides():
    from ppt_generator import build

    result = build("Sprint 42", SAMPLE_STATS, SAMPLE_NARRATIVE)
    prs = Presentation(io.BytesIO(result))

    assert len(prs.slides) == 5


def test_build_title_slide_has_sprint_name():
    from ppt_generator import build

    result = build("Sprint 42", SAMPLE_STATS, SAMPLE_NARRATIVE)
    prs = Presentation(io.BytesIO(result))

    assert "Sprint 42" in _all_text(prs.slides[0])


def test_build_highlights_slide_has_narrative_text():
    from ppt_generator import build

    result = build("Sprint 42", SAMPLE_STATS, SAMPLE_NARRATIVE)
    prs = Presentation(io.BytesIO(result))

    assert "Shipped SSO integration" in _all_text(prs.slides[3])
    assert "DB migration blocked on DBA approval" in _all_text(prs.slides[3])


def test_build_next_steps_slide_has_carryover_keys():
    from ppt_generator import build

    result = build("Sprint 42", SAMPLE_STATS, SAMPLE_NARRATIVE)
    prs = Presentation(io.BytesIO(result))

    text = _all_text(prs.slides[4])
    assert "Unblock ENG-9 with DBA" in text
    assert "ENG-1" in text


def test_build_handles_empty_status_counts():
    from ppt_generator import build

    stats = dict(SAMPLE_STATS)
    stats["status_counts"] = {}

    result = build("Sprint 42", stats, SAMPLE_NARRATIVE)
    prs = Presentation(io.BytesIO(result))

    assert len(prs.slides) == 5
    assert "No status data available." in _all_text(prs.slides[2])
