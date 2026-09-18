"""Metrics for the evaluation harness.

Two different kinds of metric, and they should not be confused:

1. Structural checks (`structural_metrics`) — deterministic, no LLM involved.
   These verify things that are objectively checkable: the concept graph has
   no cycles, curriculum order respects dependencies, every recommended
   resource has a real-looking URL, source attribution is present. These are
   ground truth.

2. LLM-judge scores (`llm_judge_metrics`) — a second model call asking a
   model to rate curriculum quality on a rubric. This is NOT ground truth:
   it's a model's opinion of another (or the same) model's output, and it can
   share blind spots with the system being evaluated. Treat it as a cheap
   proxy signal for regressions between runs, not as proof of quality. A
   trustworthy version of this eval would replace or supplement this with
   human review on a sample of runs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from studyos.llm import complete_json
from studyos.schemas import Curriculum


def structural_metrics(curriculum: Curriculum) -> dict:
    stages = curriculum.stages
    ordered_ids = [s.concept_id for s in stages]
    id_position = {cid: i for i, cid in enumerate(ordered_ids)}

    order_violations = 0
    for stage in stages:
        for dep in stage.prerequisites:
            if dep in id_position and id_position[dep] > id_position[stage.concept_id]:
                order_violations += 1

    stages_with_primary = sum(1 for s in stages if s.primary_resource is not None)
    resources_with_urls = sum(
        1
        for s in stages
        for r in ([s.primary_resource] if s.primary_resource else []) + s.alternative_resources
        + s.reference_resources + s.practice_resources
        if r.url.startswith("http")
    )
    resources_total = sum(
        len(([s.primary_resource] if s.primary_resource else []) + s.alternative_resources
            + s.reference_resources + s.practice_resources)
        for s in stages
    )

    return {
        "num_stages": len(stages),
        "prerequisite_order_violations": order_violations,  # must be 0
        "stages_with_primary_resource": stages_with_primary,
        "stages_missing_primary_resource": len(stages) - stages_with_primary,
        "resource_url_validity_rate": (
            resources_with_urls / resources_total if resources_total else None
        ),
    }


class JudgeScore(BaseModel):
    prerequisite_soundness: float = Field(ge=1, le=5)
    curriculum_relevance_to_goal: float = Field(ge=1, le=5)
    appropriate_depth_for_target_level: float = Field(ge=1, le=5)
    reasoning: str


def llm_judge_metrics(curriculum: Curriculum) -> dict:
    score = complete_json(
        prompt=(
            f"Learning goal: {curriculum.goal.model_dump_json()}\n\n"
            f"Generated curriculum (concept id, reason, prerequisites, stage order):\n"
            + "\n".join(
                f"{i+1}. {s.concept_id} — {s.reason} (depends on: {s.prerequisites})"
                for i, s in enumerate(curriculum.stages)
            )
            + "\n\nRate this curriculum 1-5 on each dimension. Be a skeptical reviewer, "
            "not a generous one — most curricula have at least one flaw worth naming."
        ),
        schema=JudgeScore,
        system="You are an experienced curriculum designer reviewing an AI-generated learning path.",
    )
    return score.model_dump()
