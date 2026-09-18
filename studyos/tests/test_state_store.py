import tempfile
from pathlib import Path

from studyos.schemas import ConceptMastery, LearnerState, MasteryLevel
from studyos.state import StateStore


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        store = StateStore(db_path)

        state = LearnerState(learner_id="rhea")
        state.completed_concept_ids = ["basics"]
        state.concept_mastery["core"] = ConceptMastery(
            concept_id="core", assessment_scores=[7, 8], mastery=MasteryLevel.PROFICIENT
        )
        store.save(state)

        loaded = store.load("rhea")
        assert loaded is not None
        assert loaded.completed_concept_ids == ["basics"]
        assert loaded.concept_mastery["core"].mastery == MasteryLevel.PROFICIENT


def test_load_missing_learner_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        store = StateStore(str(Path(tmp) / "test.db"))
        assert store.load("nobody") is None


def test_load_or_create_makes_fresh_state():
    with tempfile.TemporaryDirectory() as tmp:
        store = StateStore(str(Path(tmp) / "test.db"))
        state = store.load_or_create("new-learner")
        assert state.learner_id == "new-learner"
        assert state.curriculum is None


def test_save_overwrites_existing():
    with tempfile.TemporaryDirectory() as tmp:
        store = StateStore(str(Path(tmp) / "test.db"))
        s1 = LearnerState(learner_id="rhea", completed_concept_ids=["a"])
        store.save(s1)
        s2 = LearnerState(learner_id="rhea", completed_concept_ids=["a", "b"])
        store.save(s2)
        assert store.load("rhea").completed_concept_ids == ["a", "b"]
        assert store.list_learner_ids() == ["rhea"]
