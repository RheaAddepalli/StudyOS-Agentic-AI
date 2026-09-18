from studyos.graph.nodes import curriculum_planning
from studyos.schemas import (
    Concept,
    ConceptGraph,
    LearningGoal,
    Resource,
    ResourceKind,
    ResourceRole,
)


def test_curriculum_planning_orders_stages_and_skips_known_concepts():
    goal = LearningGoal(raw_request="learn x", topic="x", target_level="beginner")
    graph = ConceptGraph(
        concepts={
            "basics": Concept(id="basics", name="Basics", description="foundations", already_known=True),
            "core": Concept(id="core", name="Core", description="main idea", depends_on=["basics"]),
            "advanced": Concept(id="advanced", name="Advanced", description="deep dive", depends_on=["core"]),
        }
    )
    resource = Resource(
        title="Core Tutorial",
        url="https://example.com/core",
        kind=ResourceKind.TUTORIAL,
        source_tool="web_search",
        concept_id="core",
        role=ResourceRole.PRIMARY,
        estimated_minutes=45,
    )
    state = {
        "goal": goal,
        "concept_graph": graph,
        "evaluated_resources": {"core": [resource], "advanced": []},
    }

    result = curriculum_planning(state)
    curriculum = result["curriculum"]

    stage_ids = [s.concept_id for s in curriculum.stages]
    assert "basics" not in stage_ids  # already known, must not be taught
    assert stage_ids == ["core", "advanced"]  # dependency order preserved

    core_stage = curriculum.stages[0]
    assert core_stage.primary_resource.title == "Core Tutorial"
    assert core_stage.estimated_minutes == 45

    advanced_stage = curriculum.stages[1]
    assert advanced_stage.primary_resource is None  # no candidates evaluated
    assert advanced_stage.estimated_minutes == 30  # falls back to default

    assert result["stage_queue"] == ["core", "advanced"]
