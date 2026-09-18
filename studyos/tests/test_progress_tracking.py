from studyos.graph.nodes import progress_tracking_and_replan
from studyos.schemas import AssessmentResult, LearnerState, MasteryLevel


def _state(scores, weak_areas=None):
    results = [
        AssessmentResult(
            concept_id="c1",
            practice_item_id=f"p{i}",
            score=s,
            feedback="",
            weak_areas=weak_areas or [],
        )
        for i, s in enumerate(scores)
    ]
    return {
        "current_concept_id": "c1",
        "pending_results": results,
        "learner_state": LearnerState(learner_id="test"),
        "stage_queue": ["c1", "c2"],
        "log": [],
    }


def test_high_scores_advance_and_pop_queue():
    state = _state([9, 8.5])
    result = progress_tracking_and_replan(state)
    assert result["stage_queue"] == ["c2"]
    assert "c1" in result["learner_state"].completed_concept_ids
    assert result["learner_state"].concept_mastery["c1"].mastery == MasteryLevel.MASTERED


def test_low_scores_remediate_and_keep_at_front():
    state = _state([2, 3], weak_areas=["masking"])
    result = progress_tracking_and_replan(state)
    assert result["stage_queue"] == ["c1", "c2"]  # not popped
    assert "c1" not in result["learner_state"].completed_concept_ids
    mastery = result["learner_state"].concept_mastery["c1"]
    assert mastery.mastery == MasteryLevel.DEVELOPING
    assert "masking" in mastery.weak_areas


def test_last_concept_completion_sets_done():
    state = _state([9])
    state["stage_queue"] = ["c1"]
    result = progress_tracking_and_replan(state)
    assert result["stage_queue"] == []
    assert result["done"] is True
