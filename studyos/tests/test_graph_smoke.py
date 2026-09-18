"""Exercises the whole planning graph (goal -> curriculum) with the LLM and
network tool calls mocked out, so it runs offline and free in CI. This is a
wiring/integration test — it checks that state flows correctly between nodes,
not that the LLM's reasoning is good (that needs the eval harness in eval/,
against a real model).
"""

from unittest.mock import patch

from studyos.graph.build_graph import build_planning_graph
from studyos.schemas import (
    Concept,
    ConceptGraph,
    LearningGoal,
    ResourceEvaluationBatch,
    ResourceJudgment,
    ResourceRole,
)


def _fake_complete_json(prompt, schema, system="", max_tokens=2000):
    if schema is LearningGoal:
        return LearningGoal(
            raw_request="",
            topic="Testing",
            target_level="beginner",
            known_concepts=[],
        )
    if schema is ConceptGraph:
        return ConceptGraph(
            concepts={
                "basics": Concept(id="basics", name="Basics", description="the foundation"),
                "advanced": Concept(
                    id="advanced", name="Advanced", description="builds on basics",
                    depends_on=["basics"],
                ),
            }
        )
    if schema is ResourceEvaluationBatch:
        return ResourceEvaluationBatch(
            judgments=[
                ResourceJudgment(
                    index=0, include=True, role=ResourceRole.PRIMARY,
                    justification="clear and authoritative", relevance=9, authority=8,
                    estimated_minutes=25,
                )
            ]
        )
    raise AssertionError(f"unexpected schema in test: {schema}")


def _fake_web_search(query, max_results=None):
    return [{"title": f"Guide to {query}", "url": "https://example.com/guide", "snippet": "..."}]


def test_planning_graph_end_to_end():
    with patch("studyos.graph.nodes.complete_json", side_effect=_fake_complete_json), \
         patch("studyos.graph.nodes.web_search", side_effect=_fake_web_search):
        graph = build_planning_graph()
        result = graph.invoke({"raw_request": "teach me testing", "learner_id": "t1"})

    curriculum = result["curriculum"]
    stage_ids = [s.concept_id for s in curriculum.stages]
    assert stage_ids == ["basics", "advanced"]  # dependency order preserved end-to-end
    assert curriculum.stages[0].primary_resource is not None
    assert curriculum.stages[0].primary_resource.role == ResourceRole.PRIMARY
    assert result["stage_queue"] == ["basics", "advanced"]
    assert any("Learning Path Ready" in line for line in result["log"])
