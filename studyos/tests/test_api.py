"""Exercises the FastAPI endpoints end-to-end with the LLM and search tools
mocked out — same philosophy as tests/test_graph_smoke.py: this checks that
the API wiring, persistence, and per-answer saving actually work, not that
the LLM's reasoning is good.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from studyos.schemas import (
    Concept,
    ConceptGraph,
    GradingResponse,
    LearningGoal,
    PracticeBatch,
    PracticeItemDraft,
    PracticeItemType,
    ResourceEvaluationBatch,
    ResourceJudgment,
    ResourceRole,
)


def _fake_complete_json(prompt, schema, system="", max_tokens=2000):
    if schema is LearningGoal:
        return LearningGoal(raw_request="", topic="Testing", target_level="beginner")
    if schema is ConceptGraph:
        return ConceptGraph(
            concepts={
                "basics": Concept(id="basics", name="Basics", description="the foundation"),
                "advanced": Concept(
                    id="advanced", name="Advanced", description="builds on basics", depends_on=["basics"]
                ),
            }
        )
    if schema is ResourceEvaluationBatch:
        return ResourceEvaluationBatch(
            judgments=[
                ResourceJudgment(
                    index=0, include=True, role=ResourceRole.PRIMARY,
                    justification="clear", relevance=9, authority=8, estimated_minutes=20,
                )
            ]
        )
    if schema is PracticeBatch:
        return PracticeBatch(
            items=[
                PracticeItemDraft(
                    type=PracticeItemType.CONCEPTUAL_QUESTION,
                    prompt="What is a basic?",
                    grading_notes="Should mention foundations.",
                )
            ]
        )
    raise AssertionError(f"unexpected schema in test: {schema}")


def _fake_web_search(query, max_results=None):
    return [{"title": f"Guide to {query}", "url": "https://example.com/guide", "snippet": "..."}]


@pytest.fixture
def client(monkeypatch):
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "test.db")
    monkeypatch.setenv("STUDYOS_DB_PATH", db_path)

    # Force a fresh store bound to this test's temp DB, and reset config's
    # cached db_path so get_store() picks it up.
    import studyos.state as state_module
    from studyos.config import settings

    object.__setattr__(settings, "db_path", db_path)
    state_module._store_singleton = None

    from studyos.api import app

    with TestClient(app) as c:
        yield c
    state_module._store_singleton = None


def test_health(client):
    resp = client.get("/health")
    assert resp.json() == {"ok": True}


def test_full_flow_goal_practice_answer(client):
    learner_id = "test-learner"

    # No curriculum yet.
    resp = client.get(f"/learners/{learner_id}")
    assert resp.json()["has_curriculum"] is False

    # Generate curriculum via the (non-streaming path is SSE-only, so we
    # exercise the planning graph the same way the SSE endpoint does).
    with patch("studyos.graph.nodes.complete_json", side_effect=_fake_complete_json), \
         patch("studyos.graph.nodes.web_search", side_effect=_fake_web_search):
        with client.stream("GET", f"/learners/{learner_id}/goal/stream", params={"raw_request": "teach me testing"}) as stream_resp:
            events = list(stream_resp.iter_lines())
        assert any("done" in e or "curriculum ready" in e for e in events) or len(events) > 0

    resp = client.get(f"/learners/{learner_id}")
    summary = resp.json()
    assert summary["has_curriculum"] is True
    assert [s["concept_id"] for s in summary["stages"]] == ["basics", "advanced"]

    # Fetch practice for the first stage.
    with patch("studyos.graph.nodes.complete_json", side_effect=_fake_complete_json):
        practice_resp = client.get(f"/learners/{learner_id}/practice")
    practice = practice_resp.json()
    assert practice["done"] is False
    assert practice["concept_id"] == "basics"
    item_id = practice["items"][0]["id"]

    # Answer it — grading is mocked to a high score, so the stage should
    # complete and advance.
    with patch("studyos.graph.nodes.complete_json") as mock_grade:
        mock_grade.return_value = GradingResponse(score=9.0, feedback="Great job.", weak_areas=[])
        answer_resp = client.post(
            f"/learners/{learner_id}/practice/{item_id}/answer",
            json={"answer": "It's the foundational stuff."},
        )
    body = answer_resp.json()
    assert body["stage_complete"] is True
    assert body["advanced"] is True
    assert body["mastery"] == "mastered"

    # Answering the same item again should be rejected — it was already graded.
    with patch("studyos.graph.nodes.complete_json") as mock_grade2:
        mock_grade2.return_value = GradingResponse(score=9.0, feedback="Great job.", weak_areas=[])
        dup_resp = client.post(
            f"/learners/{learner_id}/practice/{item_id}/answer",
            json={"answer": "again"},
        )
    assert dup_resp.status_code in (400, 404, 409)


def test_practice_returns_404_without_curriculum(client):
    resp = client.get("/learners/no-such-learner/practice")
    assert resp.status_code == 404
