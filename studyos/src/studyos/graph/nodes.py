"""Each function here is one node in the LangGraph pipeline. Kept as plain
functions (state in, partial state out) rather than classes — LangGraph nodes
are just callables, and there's no shared mutable object that would justify a
class here.
"""

from __future__ import annotations

import uuid

from ..config import settings
from ..llm import complete, complete_json
from ..schemas import (
    Concept,
    ConceptGraph,
    Curriculum,
    CurriculumStage,
    EvidenceNote,
    EvidenceTag,
    GradingResponse,
    LearningGoal,
    MasteryLevel,
    PracticeBatch,
    PracticeItem,
    PracticeItemType,
    Resource,
    ResourceEvaluationBatch,
    ResourceKind,
    ResourceRole,
)
from ..tools import arxiv_search, github_search, run_python, web_search
from .state import GraphState


def _log(state: GraphState, message: str) -> None:
    state.setdefault("log", []).append(message)


# ---------------------------------------------------------------------------
# 1. Goal understanding
# ---------------------------------------------------------------------------

def goal_understanding(state: GraphState) -> GraphState:
    goal = complete_json(
        prompt=(
            "A learner wrote this request:\n\n"
            f'"{state["raw_request"]}"\n\n'
            "Extract a structured learning goal from it. If the learner didn't "
            "state a constraint (hours per day, deadline, format), leave it null "
            "rather than inventing a number. `topic` should be a short noun "
            "phrase naming the subject, not the whole sentence."
        ),
        schema=LearningGoal,
        system="You convert free-text learning requests into structured goals for a curriculum planner.",
    )
    goal.raw_request = state["raw_request"]
    state["goal"] = goal
    _log(state, f'Analyzing goal...\n\u2713 Identified target level: {goal.target_level}')
    return state


# ---------------------------------------------------------------------------
# 2. Prerequisite / curriculum reasoning -> concept dependency graph
# ---------------------------------------------------------------------------

def prerequisite_reasoning(state: GraphState) -> GraphState:
    goal = state["goal"]
    graph = complete_json(
        prompt=(
            f"Learning goal: {goal.model_dump_json(indent=2)}\n\n"
            "Build a prerequisite dependency graph of the concepts required to "
            "reach the target level for this specific goal. Rules:\n"
            "- Do not use a generic fixed curriculum for this subject; reason from "
            "the goal itself.\n"
            "- Mark a concept already_known=true if it is implied by the learner's "
            "known_concepts, and do not add unnecessary beginner concepts for it.\n"
            "- Every `depends_on` id must refer to another concept id in this same graph.\n"
            "- Assign each concept a learning_type: practical, conceptual, "
            "implementation, or research. Use 'research' only for concepts that "
            "genuinely need paper-level depth (respect goal.wants_research_depth).\n"
            "- Concept ids must be short kebab-case slugs, unique within the graph.\n"
            "- Favor fewer, meaningfully-sized concepts over splitting every small "
            "sub-topic into its own node. For a typical beginner-to-intermediate goal, "
            "aim for roughly 6-12 concepts total — group closely related ideas (e.g. "
            "'variables, operators, and control flow' can be one concept, not three) "
            "rather than atomizing them. Only exceed that range if the goal is "
            "genuinely broad or explicitly wants research-level depth."
        ),
        schema=ConceptGraph,
        system="You design prerequisite-aware curricula for arbitrary technical and non-technical subjects.",
        max_tokens=3000,
    )
    graph.topological_order()
    state["concept_graph"] = graph
    n_new = sum(1 for c in graph.concepts.values() if not c.already_known)
    _log(state, f"Identifying prerequisites...\n\u2713 Found {n_new} concepts to learn ({len(graph.concepts) - n_new} already known)")
    return state


# ---------------------------------------------------------------------------
# 3. Research — dynamic resource discovery per concept
# ---------------------------------------------------------------------------

def research(state: GraphState) -> GraphState:
    graph = state["concept_graph"]
    goal = state["goal"]
    candidates: dict[str, list[dict]] = {}
    emit = state.get("on_progress")

    to_research = [c for c in graph.concepts.values() if not c.already_known]
    for idx, concept in enumerate(to_research, start=1):
        if emit:
            emit(f"  researching '{concept.name}' ({idx}/{len(to_research)})")
        query = f"{concept.name} {goal.topic}"
        found: list[dict] = []

        try:
            for r in web_search(query):
                r["_tool"] = "web_search"
                r["_kind"] = ResourceKind.TUTORIAL.value
                found.append(r)
        except Exception as e:
            _log(state, f"  (web_search failed for '{concept.name}': {e})")

        if concept.learning_type == "implementation":
            try:
                for r in github_search(f"{concept.name} {goal.topic} implementation"):
                    r["_tool"] = "github_search"
                    r["_kind"] = ResourceKind.REPO.value
                    r["_snippet_field"] = "description"
                    found.append(r)
            except Exception as e:
                _log(state, f"  (github_search failed for '{concept.name}': {e})")

        if concept.learning_type == "research" or goal.wants_research_depth:
            try:
                for r in arxiv_search(f"{concept.name} {goal.topic}"):
                    r["_tool"] = "arxiv_search"
                    r["_kind"] = ResourceKind.PAPER.value
                    r["_snippet_field"] = "summary"
                    found.append(r)
            except Exception as e:
                _log(state, f"  (arxiv_search failed for '{concept.name}': {e})")

        candidates[concept.id] = found

    state["research_candidates"] = candidates
    total = sum(len(v) for v in candidates.values())
    _log(state, f"Researching resources...\n\u2713 Found {total} candidate resources across {len(candidates)} concepts")
    return state


# ---------------------------------------------------------------------------
# 4. Resource evaluation — rank and role-assign candidates per concept
# ---------------------------------------------------------------------------

def resource_evaluation(state: GraphState) -> GraphState:
    graph = state["concept_graph"]
    candidates = state["research_candidates"]
    evaluated: dict[str, list[Resource]] = {}
    evidence_notes = state.setdefault("evidence_notes", [])
    total_evaluated = 0
    emit = state.get("on_progress")

    non_empty = [cid for cid, raw in candidates.items() if raw]
    evaluated_so_far = 0
    for concept_id, raw_list in candidates.items():
        if not raw_list:
            evaluated[concept_id] = []
            continue

        concept = graph.concepts[concept_id]
        evaluated_so_far += 1
        if emit:
            emit(f"  evaluating resources for '{concept.name}' ({evaluated_so_far}/{len(non_empty)})")
        listing = "\n".join(
            f"[{i}] title={r.get('title','')!r} url={r.get('url','')!r} "
            f"snippet={r.get(r.get('_snippet_field','snippet'), '')[:120]!r}"
            for i, r in enumerate(raw_list)
        )
        batch = complete_json(
            prompt=(
                f"Concept: {concept.name} — {concept.description}\n"
                f"Learner target level: {state['goal'].target_level}\n\n"
                f"Candidate resources:\n{listing}\n\n"
                "Judge each candidate. Set include=false for anything irrelevant, "
                "redundant with a better candidate, or too low-quality to recommend. "
                "Among included candidates, assign exactly one role='primary' "
                "(the resource the learner should follow), and use 'alternative', "
                "'reference', or 'practice' for the rest as appropriate."
            ),
            schema=ResourceEvaluationBatch,
            system="You evaluate learning resources for relevance, authority, and fit to a learner's level.",
            max_tokens=1500,
        )

        resources = []
        for j in batch.judgments:
            if not j.include or not (0 <= j.index < len(raw_list)):
                continue
            raw = raw_list[j.index]
            resources.append(
                Resource(
                    title=raw.get("title", ""),
                    url=raw.get("url", ""),
                    kind=ResourceKind(raw.get("_kind", ResourceKind.TUTORIAL.value)),
                    source_tool=raw.get("_tool", "unknown"),
                    concept_id=concept_id,
                    role=j.role,
                    justification=j.justification,
                    scores={"relevance": j.relevance, "authority": j.authority},
                    estimated_minutes=j.estimated_minutes,
                )
            )
            evidence_notes.append(
                EvidenceNote(
                    tag=EvidenceTag.RETRIEVED,
                    statement=f"{raw.get('title','')} recommended as {j.role.value} for {concept.name}",
                    source_urls=[raw.get("url", "")],
                )
            )
        evaluated[concept_id] = resources
        total_evaluated += len(raw_list)

    state["evaluated_resources"] = evaluated
    _log(state, f"Evaluating resources...\n\u2713 Evaluated {total_evaluated} resources")
    return state


# ---------------------------------------------------------------------------
# 5. Curriculum planning — deterministic assembly, no LLM call
# ---------------------------------------------------------------------------

def curriculum_planning(state: GraphState) -> GraphState:
    graph = state["concept_graph"]
    evaluated: dict[str, list[Resource]] = state["evaluated_resources"]
    order = [cid for cid in graph.topological_order() if not graph.concepts[cid].already_known]

    stages = []
    for cid in order:
        concept = graph.concepts[cid]
        resources = evaluated.get(cid, [])
        primary = next((r for r in resources if r.role == ResourceRole.PRIMARY), None)
        alternatives = [r for r in resources if r.role == ResourceRole.ALTERNATIVE]
        references = [r for r in resources if r.role == ResourceRole.REFERENCE]
        practice = [r for r in resources if r.role == ResourceRole.PRACTICE]

        reason = concept.description
        if concept.depends_on:
            dep_names = [graph.concepts[d].name for d in concept.depends_on if d in graph.concepts]
            reason += f" Builds on: {', '.join(dep_names)}."

        est = primary.estimated_minutes if primary and primary.estimated_minutes else 30

        stages.append(
            CurriculumStage(
                concept_id=cid,
                reason=reason,
                prerequisites=concept.depends_on,
                primary_resource=primary,
                alternative_resources=alternatives,
                reference_resources=references,
                practice_resources=practice,
                estimated_minutes=est,
            )
        )

    curriculum = Curriculum(goal=state["goal"], stages=stages)
    state["curriculum"] = curriculum
    state["stage_queue"] = [s.concept_id for s in stages]
    _log(state, f"Building curriculum...\n\u2713 Created {len(stages)} learning stages\n\nLearning Path Ready")
    return state


# ---------------------------------------------------------------------------
# 6. Practice generation
# ---------------------------------------------------------------------------

def practice_generation(state: GraphState) -> GraphState:
    queue = state.get("stage_queue", [])
    if not queue:
        state["done"] = True
        return state

    cid = queue[0]
    state["current_concept_id"] = cid
    graph = state["concept_graph"]
    concept = graph.concepts[cid]

    existing_mastery = state.get("learner_state").concept_mastery.get(cid) if state.get("learner_state") else None
    remediation_note = ""
    if existing_mastery and existing_mastery.mastery == MasteryLevel.DEVELOPING:
        weak = ", ".join(existing_mastery.weak_areas) or "the core idea"
        remediation_note = (
            f"\n\nThe learner already attempted this concept and struggled, "
            f"specifically with: {weak}. This time: give a simpler restated "
            f"explanation first (as the prompt text of a revision item), then "
            f"easier practice items than a first attempt would get."
        )

    batch = complete_json(
        prompt=(
            f"Concept: {concept.name} — {concept.description}\n"
            f"Learning type: {concept.learning_type}\n"
            f"Target level: {state['goal'].target_level}"
            f"{remediation_note}\n\n"
            "Generate EXACTLY 5 practice items for this concept: a mix appropriate to "
            "its learning_type (conceptual questions for 'conceptual', coding "
            "exercises with runnable starter_code and a reference_solution for "
            "'implementation' or 'practical' Python-related concepts, revision "
            "questions otherwise). grading_notes should describe what a grader "
            "should check for, in plain language.\n\n"
            "CRITICAL for coding exercises: starter_code must be an INCOMPLETE "
            "skeleton — a function signature, a comment describing what to fill "
            "in, or a partial snippet with the key logic missing. It must NEVER "
            "contain a working solution; if starter_code would already produce "
            "the correct output as-is, the exercise is pointless. The actual "
            "correct answer belongs ONLY in reference_solution, which the "
            "learner never sees — it exists purely so a grader can compare "
            "against it."
        ),
        schema=PracticeBatch,
        system="You write practice exercises and self-check questions for a learning platform.",
        max_tokens=2500,
    )

    items = [
        PracticeItem(
            id=str(uuid.uuid4())[:8],
            concept_id=cid,
            type=d.type,
            prompt=d.prompt,
            starter_code=d.starter_code,
            reference_solution=d.reference_solution,
            grading_notes=d.grading_notes,
        )
        for d in batch.items[:5]  # hard cap even if the model overshoots the "exactly 5" instruction
    ]
    state["practice_items"] = items
    _log(state, f"Generated {len(items)} practice item(s) for '{concept.name}'")
    return state


# ---------------------------------------------------------------------------
# 7. Assessment — grades learner answers, running code where relevant
# ---------------------------------------------------------------------------

def grade_practice_item(item: PracticeItem, learner_answer: str) -> GradingResponse:
    execution_context = ""
    if item.type == PracticeItemType.CODING_EXERCISE:
        result = run_python(learner_answer)
        execution_context = (
            f"\n\nProgram stdout:\n{result.stdout}\n"
            f"Program stderr:\n{result.stderr}\n"
            f"Exit code: {result.exit_code}, timed out: {result.timed_out}"
        )

    return complete_json(
        prompt=(
            f"Exercise: {item.prompt}\n"
            f"What to check: {item.grading_notes}\n"
            f"Reference solution (if any): {item.reference_solution or 'N/A'}\n\n"
            f"Learner's answer:\n{learner_answer}"
            f"{execution_context}\n\n"
            "Score 0-10. Base the score on correctness and understanding "
            "demonstrated, not on matching the reference solution verbatim."
        ),
        schema=GradingResponse,
        system="You grade learner submissions fairly, generously for genuine understanding, strictly for wrong core concepts.",
    )


# ---------------------------------------------------------------------------
# 8 & 9. Progress tracking + adaptive replanning
# ---------------------------------------------------------------------------

def _mastery_from_scores(scores: list[float]) -> MasteryLevel:
    if not scores:
        return MasteryLevel.NOT_STARTED
    avg = sum(scores) / len(scores)
    if avg >= 8.5:
        return MasteryLevel.MASTERED
    if avg >= 6.5:
        return MasteryLevel.PROFICIENT
    if avg >= 3:
        return MasteryLevel.DEVELOPING
    return MasteryLevel.DEVELOPING


def progress_tracking_and_replan(state: GraphState) -> GraphState:
    results = state.get("pending_results", [])
    cid = state["current_concept_id"]
    learner_state = state["learner_state"]

    scores = [r.score for r in results]
    weak_areas = sorted({area for r in results for area in r.weak_areas})

    mastery = learner_state.concept_mastery.get(cid)
    if mastery is None:
        from ..schemas import ConceptMastery
        mastery = ConceptMastery(concept_id=cid)
    mastery.assessment_scores.extend(scores)
    mastery.mastery = _mastery_from_scores(mastery.assessment_scores)
    mastery.weak_areas = weak_areas if mastery.mastery == MasteryLevel.DEVELOPING else []
    learner_state.concept_mastery[cid] = mastery

    queue = state.get("stage_queue", [])
    if mastery.mastery in (MasteryLevel.MASTERED, MasteryLevel.PROFICIENT):
        if queue and queue[0] == cid:
            queue = queue[1:]
        learner_state.completed_concept_ids.append(cid)
        _log(state, f"'{cid}' mastery: {mastery.mastery.value} \u2192 advancing")
    else:
        _log(state, f"'{cid}' mastery: {mastery.mastery.value} \u2192 remediation needed")

    state["stage_queue"] = queue
    state["pending_results"] = []
    learner_state.history_log.extend(state.get("log", [])[-3:])
    state["learner_state"] = learner_state

    if not queue:
        state["done"] = True
    return state


def route_after_replan(state: GraphState) -> str:
    if state.get("done"):
        return "complete"
    return "continue"



































# 7 sep
# """Each function here is one node in the LangGraph pipeline. Kept as plain
# functions (state in, partial state out) rather than classes — LangGraph nodes
# are just callables, and there's no shared mutable object that would justify a
# class here.

# Node responsibilities map directly onto the spec's list: goal understanding,
# prerequisite reasoning, research, resource evaluation, curriculum planning,
# practice generation, assessment, progress tracking, adaptive replanning.
# """

# from __future__ import annotations

# import uuid

# from ..config import settings
# from ..llm import complete, complete_json
# from ..schemas import (
#     Concept,
#     ConceptGraph,
#     Curriculum,
#     CurriculumStage,
#     EvidenceNote,
#     EvidenceTag,
#     GradingResponse,
#     LearningGoal,
#     MasteryLevel,
#     PracticeBatch,
#     PracticeItem,
#     PracticeItemType,
#     Resource,
#     ResourceEvaluationBatch,
#     ResourceKind,
#     ResourceRole,
# )
# from ..tools import arxiv_search, github_search, run_python, web_search
# from .state import GraphState


# def _log(state: GraphState, message: str) -> None:
#     state.setdefault("log", []).append(message)


# # ---------------------------------------------------------------------------
# # 1. Goal understanding
# # ---------------------------------------------------------------------------

# def goal_understanding(state: GraphState) -> GraphState:
#     goal = complete_json(
#         prompt=(
#             "A learner wrote this request:\n\n"
#             f'"{state["raw_request"]}"\n\n'
#             "Extract a structured learning goal from it. If the learner didn't "
#             "state a constraint (hours per day, deadline, format), leave it null "
#             "rather than inventing a number. `topic` should be a short noun "
#             "phrase naming the subject, not the whole sentence."
#         ),
#         schema=LearningGoal,
#         system="You convert free-text learning requests into structured goals for a curriculum planner.",
#     )
#     goal.raw_request = state["raw_request"]
#     state["goal"] = goal
#     _log(state, f'Analyzing goal...\n\u2713 Identified target level: {goal.target_level}')
#     return state


# # ---------------------------------------------------------------------------
# # 2. Prerequisite / curriculum reasoning -> concept dependency graph
# # ---------------------------------------------------------------------------

# def prerequisite_reasoning(state: GraphState) -> GraphState:
#     goal = state["goal"]
#     graph = complete_json(
#         prompt=(
#             f"Learning goal: {goal.model_dump_json(indent=2)}\n\n"
#             "Build a prerequisite dependency graph of the concepts required to "
#             "reach the target level for this specific goal. Rules:\n"
#             "- Do not use a generic fixed curriculum for this subject; reason from "
#             "the goal itself.\n"
#             "- Mark a concept already_known=true if it is implied by the learner's "
#             "known_concepts, and do not add unnecessary beginner concepts for it.\n"
#             "- Every `depends_on` id must refer to another concept id in this same graph.\n"
#             "- Assign each concept a learning_type: practical, conceptual, "
#             "implementation, or research. Use 'research' only for concepts that "
#             "genuinely need paper-level depth (respect goal.wants_research_depth).\n"
#             "- Concept ids must be short kebab-case slugs, unique within the graph.\n"
#             "- Favor fewer, meaningfully-sized concepts over splitting every small "
#             "sub-topic into its own node. For a typical beginner-to-intermediate goal, "
#             "aim for roughly 6-12 concepts total — group closely related ideas (e.g. "
#             "'variables, operators, and control flow' can be one concept, not three) "
#             "rather than atomizing them. Only exceed that range if the goal is "
#             "genuinely broad or explicitly wants research-level depth."
#         ),
        
#         schema=ConceptGraph,
#         system="You design prerequisite-aware curricula for arbitrary technical and non-technical subjects.",
#         max_tokens=3000,
#     )
#     # Fail fast on a malformed graph rather than let a cycle surface later as a
#     # confusing ordering bug in curriculum_planning.
#     graph.topological_order()
#     state["concept_graph"] = graph
#     n_new = sum(1 for c in graph.concepts.values() if not c.already_known)
#     _log(state, f"Identifying prerequisites...\n\u2713 Found {n_new} concepts to learn ({len(graph.concepts) - n_new} already known)")
#     return state


# # ---------------------------------------------------------------------------
# # 3. Research — dynamic resource discovery per concept
# # ---------------------------------------------------------------------------

# def research(state: GraphState) -> GraphState:
#     graph = state["concept_graph"]
#     goal = state["goal"]
#     candidates: dict[str, list[dict]] = {}

#     for concept in graph.concepts.values():
#         if concept.already_known:
#             continue
#         query = f"{concept.name} {goal.topic}"
#         found: list[dict] = []

#         try:
#             for r in web_search(query):
#                 r["_tool"] = "web_search"
#                 r["_kind"] = ResourceKind.TUTORIAL.value
#                 found.append(r)
#         except Exception as e:
#             _log(state, f"  (web_search failed for '{concept.name}': {e})")

#         if concept.learning_type == "implementation":
#             try:
#                 for r in github_search(f"{concept.name} {goal.topic} implementation"):
#                     r["_tool"] = "github_search"
#                     r["_kind"] = ResourceKind.REPO.value
#                     r["_snippet_field"] = "description"
#                     found.append(r)
#             except Exception as e:
#                 _log(state, f"  (github_search failed for '{concept.name}': {e})")

#         if concept.learning_type == "research" or goal.wants_research_depth:
#             try:
#                 for r in arxiv_search(f"{concept.name} {goal.topic}"):
#                     r["_tool"] = "arxiv_search"
#                     r["_kind"] = ResourceKind.PAPER.value
#                     r["_snippet_field"] = "summary"
#                     found.append(r)
#             except Exception as e:
#                 _log(state, f"  (arxiv_search failed for '{concept.name}': {e})")

#         candidates[concept.id] = found

#     state["research_candidates"] = candidates
#     total = sum(len(v) for v in candidates.values())
#     _log(state, f"Researching resources...\n\u2713 Found {total} candidate resources across {len(candidates)} concepts")
#     return state


# # ---------------------------------------------------------------------------
# # 4. Resource evaluation — rank and role-assign candidates per concept
# # ---------------------------------------------------------------------------

# def resource_evaluation(state: GraphState) -> GraphState:
#     graph = state["concept_graph"]
#     candidates = state["research_candidates"]
#     evaluated: dict[str, list[Resource]] = {}
#     evidence_notes = state.setdefault("evidence_notes", [])
#     total_evaluated = 0

#     for concept_id, raw_list in candidates.items():
#         if not raw_list:
#             evaluated[concept_id] = []
#             continue

#         concept = graph.concepts[concept_id]
#         listing = "\n".join(
#             f"[{i}] title={r.get('title','')!r} url={r.get('url','')!r} "
#             f"snippet={r.get(r.get('_snippet_field','snippet'), '')[:120]!r}"
#             for i, r in enumerate(raw_list)
#         )
#         batch = complete_json(
#             prompt=(
#                 f"Concept: {concept.name} — {concept.description}\n"
#                 f"Learner target level: {state['goal'].target_level}\n\n"
#                 f"Candidate resources:\n{listing}\n\n"
#                 "Judge each candidate. Set include=false for anything irrelevant, "
#                 "redundant with a better candidate, or too low-quality to recommend. "
#                 "Among included candidates, assign exactly one role='primary' "
#                 "(the resource the learner should follow), and use 'alternative', "
#                 "'reference', or 'practice' for the rest as appropriate."
#             ),
#             schema=ResourceEvaluationBatch,
#             system="You evaluate learning resources for relevance, authority, and fit to a learner's level.",
#             max_tokens=1500,
#         )

#         resources = []
#         for j in batch.judgments:
#             if not j.include or not (0 <= j.index < len(raw_list)):
#                 continue
#             raw = raw_list[j.index]
#             resources.append(
#                 Resource(
#                     title=raw.get("title", ""),
#                     url=raw.get("url", ""),
#                     kind=ResourceKind(raw.get("_kind", ResourceKind.TUTORIAL.value)),
#                     source_tool=raw.get("_tool", "unknown"),
#                     concept_id=concept_id,
#                     role=j.role,
#                     justification=j.justification,
#                     scores={"relevance": j.relevance, "authority": j.authority},
#                     estimated_minutes=j.estimated_minutes,
#                 )
#             )
#             evidence_notes.append(
#                 EvidenceNote(
#                     tag=EvidenceTag.RETRIEVED,
#                     statement=f"{raw.get('title','')} recommended as {j.role.value} for {concept.name}",
#                     source_urls=[raw.get("url", "")],
#                 )
#             )
#         evaluated[concept_id] = resources
#         total_evaluated += len(raw_list)

#     state["evaluated_resources"] = evaluated
#     _log(state, f"Evaluating resources...\n\u2713 Evaluated {total_evaluated} resources")
#     return state


# # ---------------------------------------------------------------------------
# # 5. Curriculum planning — deterministic assembly, no LLM call
# # ---------------------------------------------------------------------------

# def curriculum_planning(state: GraphState) -> GraphState:
#     graph = state["concept_graph"]
#     evaluated: dict[str, list[Resource]] = state["evaluated_resources"]
#     order = [cid for cid in graph.topological_order() if not graph.concepts[cid].already_known]

#     stages = []
#     for cid in order:
#         concept = graph.concepts[cid]
#         resources = evaluated.get(cid, [])
#         primary = next((r for r in resources if r.role == ResourceRole.PRIMARY), None)
#         alternatives = [r for r in resources if r.role == ResourceRole.ALTERNATIVE]
#         references = [r for r in resources if r.role == ResourceRole.REFERENCE]
#         practice = [r for r in resources if r.role == ResourceRole.PRACTICE]

#         reason = concept.description
#         if concept.depends_on:
#             dep_names = [graph.concepts[d].name for d in concept.depends_on if d in graph.concepts]
#             reason += f" Builds on: {', '.join(dep_names)}."

#         est = primary.estimated_minutes if primary and primary.estimated_minutes else 30

#         stages.append(
#             CurriculumStage(
#                 concept_id=cid,
#                 reason=reason,
#                 prerequisites=concept.depends_on,
#                 primary_resource=primary,
#                 alternative_resources=alternatives,
#                 reference_resources=references,
#                 practice_resources=practice,
#                 estimated_minutes=est,
#             )
#         )

#     curriculum = Curriculum(goal=state["goal"], stages=stages)
#     state["curriculum"] = curriculum
#     state["stage_queue"] = [s.concept_id for s in stages]
#     _log(state, f"Building curriculum...\n\u2713 Created {len(stages)} learning stages\n\nLearning Path Ready")
#     return state


# # ---------------------------------------------------------------------------
# # 6. Practice generation
# # ---------------------------------------------------------------------------

# def practice_generation(state: GraphState) -> GraphState:
#     queue = state.get("stage_queue", [])
#     if not queue:
#         state["done"] = True
#         return state

#     cid = queue[0]
#     state["current_concept_id"] = cid
#     graph = state["concept_graph"]
#     concept = graph.concepts[cid]

#     existing_mastery = state.get("learner_state").concept_mastery.get(cid) if state.get("learner_state") else None
#     remediation_note = ""
#     if existing_mastery and existing_mastery.mastery == MasteryLevel.DEVELOPING:
#         weak = ", ".join(existing_mastery.weak_areas) or "the core idea"
#         remediation_note = (
#             f"\n\nThe learner already attempted this concept and struggled, "
#             f"specifically with: {weak}. This time: give a simpler restated "
#             f"explanation first (as the prompt text of a revision item), then "
#             f"easier practice items than a first attempt would get."
#         )

#     batch = complete_json(
#         prompt=(
#             f"Concept: {concept.name} — {concept.description}\n"
#             f"Learning type: {concept.learning_type}\n"
#             f"Target level: {state['goal'].target_level}"
#             f"{remediation_note}\n\n"
#             "Generate 2-4 practice items for this concept: a mix appropriate to "
#             "its learning_type (conceptual questions for 'conceptual', coding "
#             "exercises with runnable starter_code and a reference_solution for "
#             "'implementation' or 'practical' Python-related concepts, revision "
#             "questions otherwise). grading_notes should describe what a grader "
#             "should check for, in plain language."
#         ),
#         schema=PracticeBatch,
#         system="You write practice exercises and self-check questions for a learning platform.",
#         max_tokens=2500,
#     )

#     items = [
#         PracticeItem(
#             id=str(uuid.uuid4())[:8],
#             concept_id=cid,
#             type=d.type,
#             prompt=d.prompt,
#             starter_code=d.starter_code,
#             reference_solution=d.reference_solution,
#             grading_notes=d.grading_notes,
#         )
#         for d in batch.items
#     ]
#     state["practice_items"] = items
#     _log(state, f"Generated {len(items)} practice item(s) for '{concept.name}'")
#     return state


# # ---------------------------------------------------------------------------
# # 7. Assessment — grades learner answers, running code where relevant
# # ---------------------------------------------------------------------------

# def grade_practice_item(item: PracticeItem, learner_answer: str) -> GradingResponse:
#     """Exposed as a standalone function (not just inside a node) so the CLI
#     and tests can call it directly per-answer, since assessment is inherently
#     interactive rather than something the graph can do in one batch step."""
#     execution_context = ""
#     if item.type == PracticeItemType.CODING_EXERCISE:
#         result = run_python(learner_answer)
#         execution_context = (
#             f"\n\nProgram stdout:\n{result.stdout}\n"
#             f"Program stderr:\n{result.stderr}\n"
#             f"Exit code: {result.exit_code}, timed out: {result.timed_out}"
#         )

#     return complete_json(
#         prompt=(
#             f"Exercise: {item.prompt}\n"
#             f"What to check: {item.grading_notes}\n"
#             f"Reference solution (if any): {item.reference_solution or 'N/A'}\n\n"
#             f"Learner's answer:\n{learner_answer}"
#             f"{execution_context}\n\n"
#             "Score 0-10. Base the score on correctness and understanding "
#             "demonstrated, not on matching the reference solution verbatim."
#         ),
#         schema=GradingResponse,
#         system="You grade learner submissions fairly, generously for genuine understanding, strictly for wrong core concepts.",
#     )


# # ---------------------------------------------------------------------------
# # 8 & 9. Progress tracking + adaptive replanning
# # ---------------------------------------------------------------------------

# def _mastery_from_scores(scores: list[float]) -> MasteryLevel:
#     if not scores:
#         return MasteryLevel.NOT_STARTED
#     avg = sum(scores) / len(scores)
#     if avg >= 8.5:
#         return MasteryLevel.MASTERED
#     if avg >= 6.5:
#         return MasteryLevel.PROFICIENT
#     if avg >= 3:
#         return MasteryLevel.DEVELOPING
#     return MasteryLevel.DEVELOPING


# def progress_tracking_and_replan(state: GraphState) -> GraphState:
#     """Deterministic on purpose: mastery thresholds are rules, not model
#     judgment, so the same scores always produce the same routing decision."""
#     results = state.get("pending_results", [])
#     cid = state["current_concept_id"]
#     learner_state = state["learner_state"]

#     scores = [r.score for r in results]
#     weak_areas = sorted({area for r in results for area in r.weak_areas})

#     mastery = learner_state.concept_mastery.get(cid)
#     if mastery is None:
#         from ..schemas import ConceptMastery
#         mastery = ConceptMastery(concept_id=cid)
#     mastery.assessment_scores.extend(scores)
#     mastery.mastery = _mastery_from_scores(mastery.assessment_scores)
#     mastery.weak_areas = weak_areas if mastery.mastery == MasteryLevel.DEVELOPING else []
#     learner_state.concept_mastery[cid] = mastery

#     queue = state.get("stage_queue", [])
#     if mastery.mastery in (MasteryLevel.MASTERED, MasteryLevel.PROFICIENT):
#         # Advance: this concept is done, drop it from the queue.
#         if queue and queue[0] == cid:
#             queue = queue[1:]
#         learner_state.completed_concept_ids.append(cid)
#         _log(state, f"'{cid}' mastery: {mastery.mastery.value} \u2192 advancing")
#     else:
#         # Remediate: keep it at the front of the queue so practice_generation
#         # runs again for the same concept, but flag it so the next generation
#         # pass can be told to simplify.
#         _log(state, f"'{cid}' mastery: {mastery.mastery.value} \u2192 remediation needed")

#     state["stage_queue"] = queue
#     state["pending_results"] = []
#     learner_state.history_log.extend(state.get("log", [])[-3:])
#     state["learner_state"] = learner_state

#     if not queue:
#         state["done"] = True
#     return state


# def route_after_replan(state: GraphState) -> str:
#     if state.get("done"):
#         return "complete"
#     return "continue"
