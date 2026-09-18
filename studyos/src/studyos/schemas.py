"""All shared data contracts. Every agent node reads and writes these types —
never raw dicts — so a mistake in one node shows up as a validation error at
the boundary instead of a silent bug three nodes later.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Goal understanding
# ---------------------------------------------------------------------------

class LearningGoal(BaseModel):
    """Structured form of the learner's free-text request."""

    raw_request: str
    topic: str
    target_level: Literal["beginner", "intermediate", "advanced", "research"]
    known_concepts: list[str] = Field(default_factory=list)
    hours_per_day: float | None = None
    deadline_days: int | None = None
    preferred_formats: list[str] = Field(default_factory=list)  # e.g. "video", "text", "interactive"
    wants_projects: bool = True
    wants_research_depth: bool = False
    notes: str = ""


# ---------------------------------------------------------------------------
# Prerequisite graph
# ---------------------------------------------------------------------------

class Concept(BaseModel):
    id: str  # slug, e.g. "self-attention"
    name: str
    description: str
    depends_on: list[str] = Field(default_factory=list)  # ids of prerequisite concepts
    already_known: bool = False
    learning_type: Literal["practical", "conceptual", "implementation", "research"] = "conceptual"


class ConceptGraph(BaseModel):
    concepts: dict[str, Concept] = Field(default_factory=dict)

    def topological_order(self) -> list[str]:
        """Kahn's algorithm. Raises if the graph has a cycle — a cyclic
        prerequisite graph is a planning bug, not something to paper over."""
        indegree = {cid: 0 for cid in self.concepts}
        for c in self.concepts.values():
            for dep in c.depends_on:
                if dep in indegree:
                    indegree[c.id] += 1

        queue = [cid for cid, deg in indegree.items() if deg == 0]
        order: list[str] = []
        while queue:
            queue.sort()  # deterministic ordering for reproducible output
            cid = queue.pop(0)
            order.append(cid)
            for other in self.concepts.values():
                if cid in other.depends_on:
                    indegree[other.id] -= 1
                    if indegree[other.id] == 0:
                        queue.append(other.id)

        if len(order) != len(self.concepts):
            remaining = set(self.concepts) - set(order)
            raise ValueError(f"Cycle detected in prerequisite graph among: {remaining}")
        return order


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

class ResourceKind(str, Enum):
    TUTORIAL = "tutorial"
    DOCUMENTATION = "documentation"
    VIDEO = "video"
    PAPER = "paper"
    REPO = "repo"
    BOOK = "book"
    COURSE = "course"
    INTERACTIVE = "interactive"


class ResourceRole(str, Enum):
    PRIMARY = "primary"
    ALTERNATIVE = "alternative"
    REFERENCE = "reference"
    PRACTICE = "practice"


class Resource(BaseModel):
    title: str
    url: str
    kind: ResourceKind
    source_tool: str  # which MCP tool found this, e.g. "web_search", "arxiv_search"
    concept_id: str
    role: ResourceRole = ResourceRole.REFERENCE
    justification: str = ""  # why this resource was selected / this role
    scores: dict[str, float] = Field(default_factory=dict)  # relevance, authority, recency, etc.
    estimated_minutes: int | None = None
    retrieved_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Curriculum
# ---------------------------------------------------------------------------

class MasteryLevel(str, Enum):
    NOT_STARTED = "not_started"
    DEVELOPING = "developing"
    PROFICIENT = "proficient"
    MASTERED = "mastered"


class CurriculumStage(BaseModel):
    concept_id: str
    reason: str  # why this concept is needed for the learner's goal
    prerequisites: list[str] = Field(default_factory=list)
    primary_resource: Resource | None = None
    alternative_resources: list[Resource] = Field(default_factory=list)
    reference_resources: list[Resource] = Field(default_factory=list)
    practice_resources: list[Resource] = Field(default_factory=list)
    estimated_minutes: int = 0
    mastery: MasteryLevel = MasteryLevel.NOT_STARTED


class Curriculum(BaseModel):
    goal: LearningGoal
    stages: list[CurriculumStage] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)
    version: int = 1


# ---------------------------------------------------------------------------
# Practice & assessment
# ---------------------------------------------------------------------------

class PracticeItemType(str, Enum):
    QUIZ = "quiz"
    CONCEPTUAL_QUESTION = "conceptual_question"
    CODING_EXERCISE = "coding_exercise"
    IMPLEMENTATION_TASK = "implementation_task"
    PROJECT = "project"
    REVISION = "revision"


class PracticeItem(BaseModel):
    id: str
    concept_id: str
    type: PracticeItemType
    prompt: str
    starter_code: str | None = None
    reference_solution: str | None = None
    grading_notes: str = ""  # what a grader (human or LLM) should check for


class AssessmentResult(BaseModel):
    concept_id: str
    practice_item_id: str
    score: float  # 0-10
    max_score: float = 10.0
    feedback: str
    weak_areas: list[str] = Field(default_factory=list)
    answer: str = ""  # what the learner actually submitted — kept for the Submissions history view
    graded_at: datetime = Field(default_factory=_utcnow)


class SubmissionRecord(BaseModel):
    """One historical Q&A pair: the exact question asked plus the learner's
    answer and how it was graded. Kept permanently (never cleared, unlike
    active_practice_items/active_results which only track the in-progress
    session) so a learner can review everything they've ever answered for a
    concept, including ones they've already finished."""

    item: PracticeItem
    result: AssessmentResult


class ConceptMastery(BaseModel):
    concept_id: str
    assessment_scores: list[float] = Field(default_factory=list)
    implementation_scores: list[float] = Field(default_factory=list)
    mastery: MasteryLevel = MasteryLevel.NOT_STARTED
    weak_areas: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Persistent learner state
# ---------------------------------------------------------------------------

class LearningPath(BaseModel):
    """One independent learning journey — a learner can have several of
    these at once (e.g. 'python' and 'transformers' in parallel), each
    tracked completely separately: its own goal, curriculum, mastery,
    current position, and in-progress practice session."""

    path_name: str
    goal: LearningGoal | None = None
    concept_graph: ConceptGraph | None = None
    curriculum: Curriculum | None = None
    concept_mastery: dict[str, ConceptMastery] = Field(default_factory=dict)
    current_concept_id: str | None = None
    completed_concept_ids: list[str] = Field(default_factory=list)
    history_log: list[str] = Field(default_factory=list)  # human-readable trace of what happened
    active_practice_items: list[PracticeItem] = Field(default_factory=list)
    active_results: list[AssessmentResult] = Field(default_factory=list)
    submission_history: dict[str, list[SubmissionRecord]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class LearnerState(BaseModel):
    learner_id: str
    paths: dict[str, LearningPath] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Evidence / provenance — used to keep model claims separate from retrieved fact
# ---------------------------------------------------------------------------

class EvidenceTag(str, Enum):
    RETRIEVED = "retrieved"        # came directly from a tool call
    MODEL_GENERATED = "model_generated"  # LLM reasoning over retrieved evidence
    CONFLICT = "conflict"          # sources disagreed; a resolution choice was made


class EvidenceNote(BaseModel):
    tag: EvidenceTag
    statement: str
    source_urls: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM I/O wrapper schemas
# ---------------------------------------------------------------------------

class ResourceJudgment(BaseModel):
    index: int
    include: bool
    role: ResourceRole
    justification: str
    relevance: float = Field(ge=0, le=10)
    authority: float = Field(ge=0, le=10)
    estimated_minutes: int = 20


class ResourceEvaluationBatch(BaseModel):
    judgments: list[ResourceJudgment]


class PracticeItemDraft(BaseModel):
    type: PracticeItemType
    prompt: str
    starter_code: str | None = None
    reference_solution: str | None = None
    grading_notes: str = ""


class PracticeBatch(BaseModel):
    items: list[PracticeItemDraft]


class GradingResponse(BaseModel):
    score: float = Field(ge=0, le=10)
    feedback: str
    weak_areas: list[str] = Field(default_factory=list)


















# 7aug
# """All shared data contracts. Every agent node reads and writes these types —
# never raw dicts — so a mistake in one node shows up as a validation error at
# the boundary instead of a silent bug three nodes later.
# """

# from __future__ import annotations

# from datetime import datetime, timezone
# from enum import Enum
# from typing import Literal

# from pydantic import BaseModel, Field


# def _utcnow() -> datetime:
#     return datetime.now(timezone.utc)


# # ---------------------------------------------------------------------------
# # Goal understanding
# # ---------------------------------------------------------------------------

# class LearningGoal(BaseModel):
#     """Structured form of the learner's free-text request."""

#     raw_request: str
#     topic: str
#     target_level: Literal["beginner", "intermediate", "advanced", "research"]
#     known_concepts: list[str] = Field(default_factory=list)
#     hours_per_day: float | None = None
#     deadline_days: int | None = None
#     preferred_formats: list[str] = Field(default_factory=list)  # e.g. "video", "text", "interactive"
#     wants_projects: bool = True
#     wants_research_depth: bool = False
#     notes: str = ""


# # ---------------------------------------------------------------------------
# # Prerequisite graph
# # ---------------------------------------------------------------------------

# class Concept(BaseModel):
#     id: str  # slug, e.g. "self-attention"
#     name: str
#     description: str
#     depends_on: list[str] = Field(default_factory=list)  # ids of prerequisite concepts
#     already_known: bool = False
#     learning_type: Literal["practical", "conceptual", "implementation", "research"] = "conceptual"


# class ConceptGraph(BaseModel):
#     concepts: dict[str, Concept] = Field(default_factory=dict)

#     def topological_order(self) -> list[str]:
#         """Kahn's algorithm. Raises if the graph has a cycle — a cyclic
#         prerequisite graph is a planning bug, not something to paper over."""
#         indegree = {cid: 0 for cid in self.concepts}
#         for c in self.concepts.values():
#             for dep in c.depends_on:
#                 if dep in indegree:
#                     indegree[c.id] += 1

#         queue = [cid for cid, deg in indegree.items() if deg == 0]
#         order: list[str] = []
#         while queue:
#             queue.sort()  # deterministic ordering for reproducible output
#             cid = queue.pop(0)
#             order.append(cid)
#             for other in self.concepts.values():
#                 if cid in other.depends_on:
#                     indegree[other.id] -= 1
#                     if indegree[other.id] == 0:
#                         queue.append(other.id)

#         if len(order) != len(self.concepts):
#             remaining = set(self.concepts) - set(order)
#             raise ValueError(f"Cycle detected in prerequisite graph among: {remaining}")
#         return order


# # ---------------------------------------------------------------------------
# # Resources
# # ---------------------------------------------------------------------------

# class ResourceKind(str, Enum):
#     TUTORIAL = "tutorial"
#     DOCUMENTATION = "documentation"
#     VIDEO = "video"
#     PAPER = "paper"
#     REPO = "repo"
#     BOOK = "book"
#     COURSE = "course"
#     INTERACTIVE = "interactive"


# class ResourceRole(str, Enum):
#     PRIMARY = "primary"
#     ALTERNATIVE = "alternative"
#     REFERENCE = "reference"
#     PRACTICE = "practice"


# class Resource(BaseModel):
#     title: str
#     url: str
#     kind: ResourceKind
#     source_tool: str  # which MCP tool found this, e.g. "web_search", "arxiv_search"
#     concept_id: str
#     role: ResourceRole = ResourceRole.REFERENCE
#     justification: str = ""  # why this resource was selected / this role
#     scores: dict[str, float] = Field(default_factory=dict)  # relevance, authority, recency, etc.
#     estimated_minutes: int | None = None
#     retrieved_at: datetime = Field(default_factory=_utcnow)


# # ---------------------------------------------------------------------------
# # Curriculum
# # ---------------------------------------------------------------------------

# class MasteryLevel(str, Enum):
#     NOT_STARTED = "not_started"
#     DEVELOPING = "developing"
#     PROFICIENT = "proficient"
#     MASTERED = "mastered"


# class CurriculumStage(BaseModel):
#     concept_id: str
#     reason: str  # why this concept is needed for the learner's goal
#     prerequisites: list[str] = Field(default_factory=list)
#     primary_resource: Resource | None = None
#     alternative_resources: list[Resource] = Field(default_factory=list)
#     reference_resources: list[Resource] = Field(default_factory=list)
#     practice_resources: list[Resource] = Field(default_factory=list)
#     estimated_minutes: int = 0
#     mastery: MasteryLevel = MasteryLevel.NOT_STARTED


# class Curriculum(BaseModel):
#     goal: LearningGoal
#     stages: list[CurriculumStage] = Field(default_factory=list)
#     generated_at: datetime = Field(default_factory=_utcnow)
#     version: int = 1


# # ---------------------------------------------------------------------------
# # Practice & assessment
# # ---------------------------------------------------------------------------

# class PracticeItemType(str, Enum):
#     QUIZ = "quiz"
#     CONCEPTUAL_QUESTION = "conceptual_question"
#     CODING_EXERCISE = "coding_exercise"
#     IMPLEMENTATION_TASK = "implementation_task"
#     PROJECT = "project"
#     REVISION = "revision"


# class PracticeItem(BaseModel):
#     id: str
#     concept_id: str
#     type: PracticeItemType
#     prompt: str
#     starter_code: str | None = None
#     reference_solution: str | None = None
#     grading_notes: str = ""  # what a grader (human or LLM) should check for


# class AssessmentResult(BaseModel):
#     concept_id: str
#     practice_item_id: str
#     score: float  # 0-10
#     max_score: float = 10.0
#     feedback: str
#     weak_areas: list[str] = Field(default_factory=list)
#     graded_at: datetime = Field(default_factory=_utcnow)


# class ConceptMastery(BaseModel):
#     concept_id: str
#     assessment_scores: list[float] = Field(default_factory=list)
#     implementation_scores: list[float] = Field(default_factory=list)
#     mastery: MasteryLevel = MasteryLevel.NOT_STARTED
#     weak_areas: list[str] = Field(default_factory=list)


# # ---------------------------------------------------------------------------
# # Persistent learner state
# # ---------------------------------------------------------------------------

# class LearningPath(BaseModel):
#     """One independent learning journey — a learner can have several of
#     these at once (e.g. 'python' and 'transformers' in parallel), each
#     tracked completely separately: its own goal, curriculum, mastery,
#     current position, and in-progress practice session."""

#     path_name: str
#     goal: LearningGoal | None = None
#     concept_graph: ConceptGraph | None = None
#     curriculum: Curriculum | None = None
#     concept_mastery: dict[str, ConceptMastery] = Field(default_factory=dict)
#     current_concept_id: str | None = None
#     completed_concept_ids: list[str] = Field(default_factory=list)
#     history_log: list[str] = Field(default_factory=list)  # human-readable trace of what happened
#     # In-progress practice session for current_concept_id. Persisted after
#     # every single graded answer (not batched at stage end) so a learner
#     # closing the browser mid-stage never loses already-graded work — see
#     # api.py's answer endpoint.
#     active_practice_items: list[PracticeItem] = Field(default_factory=list)
#     active_results: list[AssessmentResult] = Field(default_factory=list)
#     created_at: datetime = Field(default_factory=_utcnow)
#     updated_at: datetime = Field(default_factory=_utcnow)


# class LearnerState(BaseModel):
#     learner_id: str
#     paths: dict[str, LearningPath] = Field(default_factory=dict)
#     updated_at: datetime = Field(default_factory=_utcnow)

# # ---------------------------------------------------------------------------
# # Evidence / provenance — used to keep model claims separate from retrieved fact
# # ---------------------------------------------------------------------------

# class EvidenceTag(str, Enum):
#     RETRIEVED = "retrieved"        # came directly from a tool call
#     MODEL_GENERATED = "model_generated"  # LLM reasoning over retrieved evidence
#     CONFLICT = "conflict"          # sources disagreed; a resolution choice was made


# class EvidenceNote(BaseModel):
#     tag: EvidenceTag
#     statement: str
#     source_urls: list[str] = Field(default_factory=list)


# # ---------------------------------------------------------------------------
# # LLM I/O wrapper schemas — used only as the `schema` arg to llm.complete_json.
# # Kept separate from the domain models above: these shapes exist because an
# # LLM has to produce them, not because the app needs to store them this way.
# # ---------------------------------------------------------------------------

# class ResourceJudgment(BaseModel):
#     index: int  # position of the candidate in the list passed to the prompt
#     include: bool
#     role: ResourceRole
#     justification: str
#     relevance: float = Field(ge=0, le=10)
#     authority: float = Field(ge=0, le=10)
#     estimated_minutes: int = 20


# class ResourceEvaluationBatch(BaseModel):
#     judgments: list[ResourceJudgment]


# class PracticeItemDraft(BaseModel):
#     type: PracticeItemType
#     prompt: str
#     starter_code: str | None = None
#     reference_solution: str | None = None
#     grading_notes: str = ""


# class PracticeBatch(BaseModel):
#     items: list[PracticeItemDraft]


# class GradingResponse(BaseModel):
#     score: float = Field(ge=0, le=10)
#     feedback: str
#     weak_areas: list[str] = Field(default_factory=list)
