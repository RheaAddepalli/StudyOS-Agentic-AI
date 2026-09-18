"""The LangGraph state object threaded through every node.

Deliberately holds the typed Pydantic models from schemas.py rather than raw
dicts — LangGraph doesn't require that, but "typed schemas" and "explicit
agent state" were requirements, and a TypedDict full of `dict` would satisfy
neither in spirit.

`log` is the human-readable trace the CLI prints as it runs (mirrors the
"Analyzing goal... ✓ Identified target level" style UX from the spec) and
also becomes part of LearnerState.history_log on save.
"""

from __future__ import annotations

from typing import Optional, TypedDict

from ..schemas import (
    AssessmentResult,
    ConceptGraph,
    Curriculum,
    EvidenceNote,
    LearnerState,
    LearningGoal,
    PracticeItem,
)


class GraphState(TypedDict, total=False):
    learner_id: str
    raw_request: str

    goal: LearningGoal
    concept_graph: ConceptGraph
    research_candidates: dict[str, list[dict]]  # concept_id -> raw tool results
    evaluated_resources: dict[str, list]         # concept_id -> list[Resource]
    curriculum: Curriculum

    stage_queue: list[str]        # concept_ids still to teach, in order
    current_concept_id: Optional[str]

    practice_items: list[PracticeItem]
    pending_results: list[AssessmentResult]

    learner_state: LearnerState
    evidence_notes: list[EvidenceNote]
    log: list[str]

    done: bool
