"""FastAPI backend for the StudyOS web frontend.

Run locally:
    uvicorn studyos.api:app --reload --port 8000

A learner can have several independent learning paths at once (e.g. "python"
and "transformers" in parallel) — each with its own goal, curriculum,
mastery, and in-progress practice session, identified by a short name the
learner picks. Endpoints are scoped by both `learner_id` (no password, no
auth — a single-user portfolio tool) and `path_name`:

    GET  /learners/{learner_id}/paths                    -> list of this
                                                              learner's paths
                                                              (summary only)
    GET  /learners/{learner_id}/paths/{path_name}         -> full detail for
                                                              one path
    GET  /learners/{learner_id}/paths/{path_name}/goal/stream?raw_request=...
                                                           -> SSE: builds the
                                                              curriculum for a
                                                              NEW path with
                                                              this name
    GET  /learners/{learner_id}/paths/{path_name}/concepts/{concept_id}/practice
                                                           -> practice for ANY
                                                              concept in the
                                                              curriculum, not
                                                              just the
                                                              sequential
                                                              current one
    POST /learners/{learner_id}/paths/{path_name}/concepts/{concept_id}/practice/restart
                                                           -> discard the
                                                              in-progress
                                                              question set for
                                                              this concept
    GET  /learners/{learner_id}/paths/{path_name}/concepts/{concept_id}/submissions
                                                           -> permanent Q&A
                                                              history for one
                                                              concept
    POST /learners/{learner_id}/paths/{path_name}/concepts/{concept_id}/practice/{item_id}/answer
                                                           -> grade one answer;
                                                              advances/
                                                              remediates the
                                                              real curriculum
                                                              only if this is
                                                              the actual
                                                              sequential
                                                              current concept

Design note: curriculum generation is genuinely slow (multiple LLM calls +
searches per concept), so it streams via SSE using LangGraph's `.stream()`
(which yields after every node, plus an `on_progress` callback threaded
through the slow per-concept loops in graph/nodes.py) rather than one long
blocking POST. Grading a single answer is one LLM call — fast enough for an
ordinary request/response, so it isn't streamed.
"""

from __future__ import annotations

import asyncio
from queue import Queue
from threading import Thread

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .graph.build_graph import build_planning_graph, build_progress_graph, build_replan_graph
from .graph.nodes import grade_practice_item
from .schemas import AssessmentResult, LearnerState, LearningPath, MasteryLevel, SubmissionRecord
from .state import get_store

app = FastAPI(title="StudyOS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Response shapes — kept separate from the internal schemas.py models so the
# API's public contract can stay stable even if internal fields change shape.
# ---------------------------------------------------------------------------

class PathListEntry(BaseModel):
    path_name: str
    goal_text: str | None = None
    total_stages: int = 0
    mastered_or_proficient: int = 0
    is_complete: bool = False


class PathDetail(BaseModel):
    path_name: str
    has_curriculum: bool
    goal_text: str | None = None
    stages: list[dict] = []
    current_concept_id: str | None = None
    completed_concept_ids: list[str] = []


class AnswerRequest(BaseModel):
    answer: str


class NewPathRequest(BaseModel):
    raw_request: str


def _get_path(state: LearnerState, path_name: str) -> LearningPath:
    path = state.paths.get(path_name)
    if path is None:
        raise HTTPException(404, f"No path named '{path_name}' for this learner.")
    return path


def _reconstruct_queue(path: LearningPath) -> list[str]:
    if not path.curriculum:
        return []
    return [s.concept_id for s in path.curriculum.stages if s.concept_id not in path.completed_concept_ids]


def _public_item(item) -> dict:
    """Strips reference_solution and grading_notes before a practice item
    goes over the wire — those exist purely for server-side grading and must
    never reach the browser, where dev tools would expose them as an answer
    key sitting right in the network tab."""
    return {
        "id": item.id,
        "concept_id": item.concept_id,
        "type": item.type.value,
        "prompt": item.prompt,
        "starter_code": item.starter_code,
    }


def _detail(path: LearningPath) -> PathDetail:
    stages_out = []
    if path.curriculum:
        for stage in path.curriculum.stages:
            mastery = path.concept_mastery.get(stage.concept_id)
            is_current = stage.concept_id == path.current_concept_id
            in_progress = (
                bool(path.active_practice_items)
                and path.active_practice_items[0].concept_id == stage.concept_id
                and bool(path.active_results)
                and stage.concept_id not in path.completed_concept_ids
            )
            best_score = (
                max(mastery.assessment_scores) if mastery and mastery.assessment_scores else None
            )
            stages_out.append(
                {
                    "concept_id": stage.concept_id,
                    "reason": stage.reason,
                    "prerequisites": stage.prerequisites,
                    "estimated_minutes": stage.estimated_minutes,
                    "mastery": (mastery.mastery.value if mastery else MasteryLevel.NOT_STARTED.value),
                    "in_progress": in_progress,
                    "best_score": best_score,
                    "has_submissions": bool(path.submission_history.get(stage.concept_id)),
                    "primary_resource": stage.primary_resource.model_dump() if stage.primary_resource else None,
                    "alternative_resources": [r.model_dump() for r in stage.alternative_resources],
                    "reference_resources": [r.model_dump() for r in stage.reference_resources],
                    "practice_resources": [r.model_dump() for r in stage.practice_resources],
                    "is_current": is_current,
                }
            )
    return PathDetail(
        path_name=path.path_name,
        has_curriculum=path.curriculum is not None,
        goal_text=path.goal.raw_request if path.goal else None,
        stages=stages_out,
        current_concept_id=path.current_concept_id,
        completed_concept_ids=path.completed_concept_ids,
    )


def _list_entry(path: LearningPath) -> PathListEntry:
    total = len(path.curriculum.stages) if path.curriculum else 0
    good = sum(
        1
        for m in path.concept_mastery.values()
        if m.mastery in (MasteryLevel.MASTERED, MasteryLevel.PROFICIENT)
    )
    return PathListEntry(
        path_name=path.path_name,
        goal_text=path.goal.raw_request if path.goal else None,
        total_stages=total,
        mastered_or_proficient=good,
        is_complete=total > 0 and good == total,
    )


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/learners/{learner_id}/paths", response_model=list[PathListEntry])
def list_paths(learner_id: str):
    state = get_store().load_or_create(learner_id)
    return [_list_entry(p) for p in state.paths.values()]


@app.get("/learners/{learner_id}/paths/{path_name}", response_model=PathDetail)
def get_path(learner_id: str, path_name: str):
    state = get_store().load_or_create(learner_id)
    path = _get_path(state, path_name)
    return _detail(path)


@app.get("/learners/{learner_id}/paths/{path_name}/goal/stream")
async def stream_goal(learner_id: str, path_name: str, raw_request: str):
    """SSE endpoint. Creates a brand-new path with this name (rejects if one
    already exists — pick a different name for a second topic). Runs the
    planning graph in a background thread (LangGraph's .stream() is
    synchronous) and relays each node's log lines, plus real-time
    per-concept progress from the slow nodes via on_progress, to the browser
    as they happen, then saves the finished curriculum before closing.
    """
    store = get_store()
    existing = store.load_or_create(learner_id)
    if path_name in existing.paths:
        raise HTTPException(409, f"A path named '{path_name}' already exists for this learner.")

    q: Queue = Queue()
    DONE = object()
    _last_seen = [0]

    def worker():
        try:
            graph = build_planning_graph()
            final_state = None
            for step in graph.stream(
                {
                    "raw_request": raw_request,
                    "learner_id": learner_id,
                    "on_progress": q.put,  # real-time per-concept lines from slow nodes
                },
                stream_mode="values",
            ):
                final_state = step
                for line in step.get("log", [])[_last_seen[0]:]:
                    q.put(line)
                _last_seen[0] = len(step.get("log", []))

            if final_state is None:
                q.put("__error__:planning produced no output")
                return

            learner_state = store.load_or_create(learner_id)
            path = LearningPath(
                path_name=path_name,
                goal=final_state["goal"],
                concept_graph=final_state["concept_graph"],
                curriculum=final_state["curriculum"],
            )
            if path.curriculum.stages:
                path.current_concept_id = path.curriculum.stages[0].concept_id
            learner_state.paths[path_name] = path
            store.save(learner_state)
            q.put("__done__")
        except Exception as e:  # noqa: BLE001 — surface any failure to the client, don't hang the stream
            q.put(f"__error__:{e}")
        finally:
            q.put(DONE)

    Thread(target=worker, daemon=True).start()

    async def event_generator():
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, _blocking_get, q)
            if item is DONE:
                break
            if item == "__done__":
                yield {"event": "done", "data": "curriculum ready"}
            elif isinstance(item, str) and item.startswith("__error__:"):
                yield {"event": "error", "data": item[len("__error__:"):]}
            else:
                yield {"event": "progress", "data": item}

    return EventSourceResponse(event_generator())


def _blocking_get(q: Queue):
    return q.get()


def _concept_exists(path: LearningPath, concept_id: str) -> bool:
    return bool(path.curriculum) and any(s.concept_id == concept_id for s in path.curriculum.stages)


@app.get("/learners/{learner_id}/paths/{path_name}/concepts/{concept_id}/practice")
def get_practice(learner_id: str, path_name: str, concept_id: str):
    """Practice for ANY concept in the curriculum, not just the current one
    — a learner can revisit a finished concept or jump ahead, independent of
    sequential progression. Progression (which concept is 'current', when a
    stage advances) is tracked separately and untouched by this."""
    store = get_store()
    state = store.load_or_create(learner_id)
    path = _get_path(state, path_name)
    if not path.curriculum:
        raise HTTPException(404, "No curriculum yet for this path.")
    if not _concept_exists(path, concept_id):
        raise HTTPException(404, f"No concept '{concept_id}' in this path's curriculum.")

    if not path.active_practice_items or path.active_practice_items[0].concept_id != concept_id:
        # Nothing in progress for this concept yet — generate and persist it.
        # Passing a single-item synthetic queue makes practice_generation
        # target exactly this concept regardless of where it actually sits
        # in the real curriculum order.
        progress_graph = build_progress_graph()
        result = progress_graph.invoke(
            {
                "concept_graph": path.concept_graph,
                "goal": path.goal,
                "stage_queue": [concept_id],
                "learner_state": path,
            }
        )
        path.active_practice_items = result["practice_items"]
        path.active_results = []
        store.save(state)

    answered_ids = {r.practice_item_id for r in path.active_results}
    return {
        "done": False,
        "concept_id": concept_id,
        "items": [_public_item(item) for item in path.active_practice_items],
        "answered_item_ids": list(answered_ids),
        "results": [r.model_dump() for r in path.active_results],
    }


@app.post("/learners/{learner_id}/paths/{path_name}/concepts/{concept_id}/practice/restart")
def restart_practice(learner_id: str, path_name: str, concept_id: str):
    """Discards the in-progress question set for this concept so the next
    GET .../practice generates a fresh batch. Mastery and submission_history
    are deliberately untouched — 'start over' means new questions, not
    erasing what you've already earned."""
    store = get_store()
    state = store.load_or_create(learner_id)
    path = _get_path(state, path_name)
    if not _concept_exists(path, concept_id):
        raise HTTPException(404, f"No concept '{concept_id}' in this path's curriculum.")
    if not path.active_practice_items or path.active_practice_items[0].concept_id != concept_id:
        raise HTTPException(400, f"No practice in progress for '{concept_id}'.")

    path.active_practice_items = []
    path.active_results = []
    store.save(state)
    return {"ok": True, "concept_id": concept_id}


@app.get("/learners/{learner_id}/paths/{path_name}/concepts/{concept_id}/submissions")
def get_submissions(learner_id: str, path_name: str, concept_id: str):
    """Permanent history of every question answered for one concept —
    unlike GET .../practice, this includes concepts that are already
    finished, not just the currently active one."""
    state = get_store().load_or_create(learner_id)
    path = _get_path(state, path_name)
    records = path.submission_history.get(concept_id, [])
    return [
        {
            "prompt": r.item.prompt,
            "type": r.item.type.value,
            "answer": r.result.answer,
            "score": r.result.score,
            "feedback": r.result.feedback,
            "graded_at": r.result.graded_at.isoformat(),
        }
        for r in records
    ]


@app.post("/learners/{learner_id}/paths/{path_name}/concepts/{concept_id}/practice/{item_id}/answer")
def submit_answer(learner_id: str, path_name: str, concept_id: str, item_id: str, body: AnswerRequest):
    store = get_store()
    state = store.load_or_create(learner_id)
    path = _get_path(state, path_name)
    if not path.active_practice_items:
        raise HTTPException(400, "No practice items in progress. Call GET .../practice first.")

    item = next((i for i in path.active_practice_items if i.id == item_id), None)
    if item is None or item.concept_id != concept_id:
        raise HTTPException(404, f"No practice item with id {item_id} for concept '{concept_id}'.")
    if any(r.practice_item_id == item_id for r in path.active_results):
        raise HTTPException(409, "This item was already graded.")

    grading = grade_practice_item(item, body.answer)
    result = AssessmentResult(
        concept_id=item.concept_id,
        practice_item_id=item.id,
        score=grading.score,
        feedback=grading.feedback,
        weak_areas=grading.weak_areas,
        answer=body.answer,
    )
    path.active_results.append(result)
    path.submission_history.setdefault(item.concept_id, []).append(
        SubmissionRecord(item=item, result=result)
    )
    store.save(state)

    all_answered = len(path.active_results) == len(path.active_practice_items)
    response = {
        "score": result.score,
        "feedback": result.feedback,
        "weak_areas": result.weak_areas,
        "stage_complete": False,
    }

    if all_answered:
        real_queue = _reconstruct_queue(path)
        is_sequential_current = bool(real_queue) and real_queue[0] == item.concept_id

        # Operate on a deep copy — progress_tracking_and_replan mutates
        # completed_concept_ids/stage_queue IN PLACE, and if we passed the
        # real `path` by reference, that mutation would leak through
        # regardless of which branch runs below. A copy guarantees `path`
        # only changes via the explicit assignments we choose to make.
        practice_target = path.model_copy(deep=True)
        replan_graph = build_replan_graph()
        replan_result = replan_graph.invoke(
            {
                "current_concept_id": item.concept_id,
                "pending_results": path.active_results,
                "learner_state": practice_target,
                "stage_queue": real_queue if is_sequential_current else [item.concept_id],
                "log": [],
            }
        )
        replanned_path = replan_result["learner_state"]

        path.concept_mastery[item.concept_id] = replanned_path.concept_mastery[item.concept_id]
        path.active_practice_items = []
        path.active_results = []

        if is_sequential_current:
            path.completed_concept_ids = replanned_path.completed_concept_ids
            path.history_log = replanned_path.history_log
            remaining_queue = _reconstruct_queue(path)
            path.current_concept_id = remaining_queue[0] if remaining_queue else None

        state.paths[path_name] = path
        store.save(state)

        mastery = path.concept_mastery.get(item.concept_id)
        response["stage_complete"] = True
        response["mastery"] = mastery.mastery.value if mastery else None
        response["advanced"] = item.concept_id in path.completed_concept_ids
        response["curriculum_complete"] = len(_reconstruct_queue(path)) == 0

    return response













# 7 sep
# """FastAPI backend for the StudyOS web frontend.

# Run locally:
#     uvicorn studyos.api:app --reload --port 8000

# A learner can have several independent learning paths at once (e.g. "python"
# and "transformers" in parallel) — each with its own goal, curriculum,
# mastery, and in-progress practice session, identified by a short name the
# learner picks. Endpoints are scoped by both `learner_id` (no password, no
# auth — a single-user portfolio tool) and `path_name`:

#     GET  /learners/{learner_id}/paths                    -> list of this
#                                                               learner's paths
#                                                               (summary only)
#     GET  /learners/{learner_id}/paths/{path_name}         -> full detail for
#                                                               one path
#     GET  /learners/{learner_id}/paths/{path_name}/goal/stream?raw_request=...
#                                                            -> SSE: builds the
#                                                               curriculum for a
#                                                               NEW path with
#                                                               this name
#     GET  /learners/{learner_id}/paths/{path_name}/practice
#                                                            -> practice items
#                                                               for this path's
#                                                               current concept
#     POST /learners/{learner_id}/paths/{path_name}/practice/{item_id}/answer
#                                                            -> grade one
#                                                               answer, save
#                                                               immediately,
#                                                               advance/
#                                                               remediate

# Design note: curriculum generation is genuinely slow (multiple LLM calls +
# searches per concept), so it streams via SSE using LangGraph's `.stream()`
# (which yields after every node, plus an `on_progress` callback threaded
# through the slow per-concept loops in graph/nodes.py) rather than one long
# blocking POST. Grading a single answer is one LLM call — fast enough for an
# ordinary request/response, so it isn't streamed.
# """

# from __future__ import annotations

# import asyncio
# from queue import Queue
# from threading import Thread

# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# from sse_starlette.sse import EventSourceResponse

# from .config import settings
# from .graph.build_graph import build_planning_graph, build_progress_graph, build_replan_graph
# from .graph.nodes import grade_practice_item
# from .schemas import AssessmentResult, LearnerState, LearningPath, MasteryLevel
# from .state import get_store

# app = FastAPI(title="StudyOS API")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=list(settings.allowed_origins),
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # ---------------------------------------------------------------------------
# # Response shapes — kept separate from the internal schemas.py models so the
# # API's public contract can stay stable even if internal fields change shape.
# # ---------------------------------------------------------------------------

# class PathListEntry(BaseModel):
#     path_name: str
#     goal_text: str | None = None
#     total_stages: int = 0
#     mastered_or_proficient: int = 0
#     is_complete: bool = False


# class PathDetail(BaseModel):
#     path_name: str
#     has_curriculum: bool
#     goal_text: str | None = None
#     stages: list[dict] = []
#     current_concept_id: str | None = None
#     completed_concept_ids: list[str] = []


# class AnswerRequest(BaseModel):
#     answer: str


# class NewPathRequest(BaseModel):
#     raw_request: str


# def _get_path(state: LearnerState, path_name: str) -> LearningPath:
#     path = state.paths.get(path_name)
#     if path is None:
#         raise HTTPException(404, f"No path named '{path_name}' for this learner.")
#     return path


# def _reconstruct_queue(path: LearningPath) -> list[str]:
#     if not path.curriculum:
#         return []
#     return [s.concept_id for s in path.curriculum.stages if s.concept_id not in path.completed_concept_ids]


# def _detail(path: LearningPath) -> PathDetail:
#     stages_out = []
#     if path.curriculum:
#         for stage in path.curriculum.stages:
#             mastery = path.concept_mastery.get(stage.concept_id)
#             stages_out.append(
#                 {
#                     "concept_id": stage.concept_id,
#                     "reason": stage.reason,
#                     "prerequisites": stage.prerequisites,
#                     "estimated_minutes": stage.estimated_minutes,
#                     "mastery": (mastery.mastery.value if mastery else MasteryLevel.NOT_STARTED.value),
#                     "primary_resource": stage.primary_resource.model_dump() if stage.primary_resource else None,
#                     "alternative_resources": [r.model_dump() for r in stage.alternative_resources],
#                     "reference_resources": [r.model_dump() for r in stage.reference_resources],
#                     "practice_resources": [r.model_dump() for r in stage.practice_resources],
#                     "is_current": stage.concept_id == path.current_concept_id,
#                 }
#             )
#     return PathDetail(
#         path_name=path.path_name,
#         has_curriculum=path.curriculum is not None,
#         goal_text=path.goal.raw_request if path.goal else None,
#         stages=stages_out,
#         current_concept_id=path.current_concept_id,
#         completed_concept_ids=path.completed_concept_ids,
#     )


# def _list_entry(path: LearningPath) -> PathListEntry:
#     total = len(path.curriculum.stages) if path.curriculum else 0
#     good = sum(
#         1
#         for m in path.concept_mastery.values()
#         if m.mastery in (MasteryLevel.MASTERED, MasteryLevel.PROFICIENT)
#     )
#     return PathListEntry(
#         path_name=path.path_name,
#         goal_text=path.goal.raw_request if path.goal else None,
#         total_stages=total,
#         mastered_or_proficient=good,
#         is_complete=total > 0 and good == total,
#     )


# @app.get("/health")
# def health():
#     return {"ok": True}


# @app.get("/learners/{learner_id}/paths", response_model=list[PathListEntry])
# def list_paths(learner_id: str):
#     state = get_store().load_or_create(learner_id)
#     return [_list_entry(p) for p in state.paths.values()]


# @app.get("/learners/{learner_id}/paths/{path_name}", response_model=PathDetail)
# def get_path(learner_id: str, path_name: str):
#     state = get_store().load_or_create(learner_id)
#     path = _get_path(state, path_name)
#     return _detail(path)


# @app.get("/learners/{learner_id}/paths/{path_name}/goal/stream")
# async def stream_goal(learner_id: str, path_name: str, raw_request: str):
#     """SSE endpoint. Creates a brand-new path with this name (rejects if one
#     already exists — pick a different name for a second topic). Runs the
#     planning graph in a background thread (LangGraph's .stream() is
#     synchronous) and relays each node's log lines, plus real-time
#     per-concept progress from the slow nodes via on_progress, to the browser
#     as they happen, then saves the finished curriculum before closing.
#     """
#     store = get_store()
#     existing = store.load_or_create(learner_id)
#     if path_name in existing.paths:
#         raise HTTPException(409, f"A path named '{path_name}' already exists for this learner.")

#     q: Queue = Queue()
#     DONE = object()
#     _last_seen = [0]

#     def worker():
#         try:
#             graph = build_planning_graph()
#             final_state = None
#             for step in graph.stream(
#                 {
#                     "raw_request": raw_request,
#                     "learner_id": learner_id,
#                     "on_progress": q.put,  # real-time per-concept lines from slow nodes
#                 },
#                 stream_mode="values",
#             ):
#                 final_state = step
#                 for line in step.get("log", [])[_last_seen[0]:]:
#                     q.put(line)
#                 _last_seen[0] = len(step.get("log", []))

#             if final_state is None:
#                 q.put("__error__:planning produced no output")
#                 return

#             learner_state = store.load_or_create(learner_id)
#             path = LearningPath(
#                 path_name=path_name,
#                 goal=final_state["goal"],
#                 concept_graph=final_state["concept_graph"],
#                 curriculum=final_state["curriculum"],
#             )
#             if path.curriculum.stages:
#                 path.current_concept_id = path.curriculum.stages[0].concept_id
#             learner_state.paths[path_name] = path
#             store.save(learner_state)
#             q.put("__done__")
#         except Exception as e:  # noqa: BLE001 — surface any failure to the client, don't hang the stream
#             q.put(f"__error__:{e}")
#         finally:
#             q.put(DONE)

#     Thread(target=worker, daemon=True).start()

#     async def event_generator():
#         loop = asyncio.get_event_loop()
#         while True:
#             item = await loop.run_in_executor(None, _blocking_get, q)
#             if item is DONE:
#                 break
#             if item == "__done__":
#                 yield {"event": "done", "data": "curriculum ready"}
#             elif isinstance(item, str) and item.startswith("__error__:"):
#                 yield {"event": "error", "data": item[len("__error__:"):]}
#             else:
#                 yield {"event": "progress", "data": item}

#     return EventSourceResponse(event_generator())


# def _blocking_get(q: Queue):
#     return q.get()


# @app.get("/learners/{learner_id}/paths/{path_name}/practice")
# def get_practice(learner_id: str, path_name: str):
#     store = get_store()
#     state = store.load_or_create(learner_id)
#     path = _get_path(state, path_name)
#     if not path.curriculum:
#         raise HTTPException(404, "No curriculum yet for this path.")

#     queue = _reconstruct_queue(path)
#     if not queue:
#         return {"done": True, "items": [], "results": []}

#     cid = queue[0]
#     path.current_concept_id = cid

#     if not path.active_practice_items or path.active_practice_items[0].concept_id != cid:
#         # Nothing in progress for this concept yet — generate and persist it.
#         progress_graph = build_progress_graph()
#         result = progress_graph.invoke(
#             {
#                 "concept_graph": path.concept_graph,
#                 "goal": path.goal,
#                 "stage_queue": queue,
#                 "learner_state": path,
#             }
#         )
#         path.active_practice_items = result["practice_items"]
#         path.active_results = []
#         store.save(state)

#     answered_ids = {r.practice_item_id for r in path.active_results}
#     return {
#         "done": False,
#         "concept_id": cid,
#         "items": [item.model_dump() for item in path.active_practice_items],
#         "answered_item_ids": list(answered_ids),
#         "results": [r.model_dump() for r in path.active_results],
#     }


# @app.post("/learners/{learner_id}/paths/{path_name}/practice/{item_id}/answer")
# def submit_answer(learner_id: str, path_name: str, item_id: str, body: AnswerRequest):
#     store = get_store()
#     state = store.load_or_create(learner_id)
#     path = _get_path(state, path_name)
#     if not path.active_practice_items:
#         raise HTTPException(400, "No practice items in progress. Call GET .../practice first.")

#     item = next((i for i in path.active_practice_items if i.id == item_id), None)
#     if item is None:
#         raise HTTPException(404, f"No practice item with id {item_id} in the current session.")
#     if any(r.practice_item_id == item_id for r in path.active_results):
#         raise HTTPException(409, "This item was already graded.")

#     grading = grade_practice_item(item, body.answer)
#     result = AssessmentResult(
#         concept_id=item.concept_id,
#         practice_item_id=item.id,
#         score=grading.score,
#         feedback=grading.feedback,
#         weak_areas=grading.weak_areas,
#     )
#     # Save immediately — this is the per-answer persistence the frontend
#     # design relies on: closing the tab here loses nothing already graded.
#     path.active_results.append(result)
#     store.save(state)

#     all_answered = len(path.active_results) == len(path.active_practice_items)
#     response = {
#         "score": result.score,
#         "feedback": result.feedback,
#         "weak_areas": result.weak_areas,
#         "stage_complete": False,
#     }

#     if all_answered:
#         replan_graph = build_replan_graph()
#         replan_result = replan_graph.invoke(
#             {
#                 "current_concept_id": item.concept_id,
#                 "pending_results": path.active_results,
#                 "learner_state": path,
#                 "stage_queue": _reconstruct_queue(path),
#                 "log": [],
#             }
#         )
#         path = replan_result["learner_state"]
#         path.active_practice_items = []
#         path.active_results = []
#         state.paths[path_name] = path
#         store.save(state)

#         mastery = path.concept_mastery.get(item.concept_id)
#         response["stage_complete"] = True
#         response["mastery"] = mastery.mastery.value if mastery else None
#         response["advanced"] = item.concept_id in path.completed_concept_ids
#         response["curriculum_complete"] = len(_reconstruct_queue(path)) == 0

#     return response
















# """FastAPI backend for the StudyOS web frontend.

# Run locally:
#     uvicorn studyos.api:app --reload --port 8000

# Endpoints (all learner-scoped by a plain string `learner_id` — no password,
# no auth; this is a single-user portfolio tool, not a multi-tenant product):

#     GET  /learners/{learner_id}                         -> current state summary
#     GET  /learners/{learner_id}/goal/stream?raw_request=...  -> SSE: builds the
#                                                               curriculum, streaming
#                                                               the same progress
#                                                               lines the CLI prints
#     GET  /learners/{learner_id}/practice                 -> practice items for the
#                                                               current concept
#                                                               (generates + persists
#                                                               them if not already
#                                                               in progress)
#     POST /learners/{learner_id}/practice/{item_id}/answer -> grade one answer,
#                                                               save immediately,
#                                                               advance/remediate
#                                                               once the stage is done

# Design note: curriculum generation is genuinely slow (multiple LLM calls +
# searches per concept), so it streams via SSE using LangGraph's `.stream()`
# (which yields after every node) rather than one long blocking POST. Grading a
# single answer is one LLM call — fast enough for an ordinary request/response,
# so it isn't streamed; the frontend just shows a spinner for that one.
# """

# from __future__ import annotations

# import asyncio
# from queue import Queue
# from threading import Thread

# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# from sse_starlette.sse import EventSourceResponse

# from .config import settings
# from .graph.build_graph import build_planning_graph, build_progress_graph, build_replan_graph
# from .graph.nodes import grade_practice_item
# from .schemas import AssessmentResult, LearnerState, MasteryLevel
# from .state import get_store

# app = FastAPI(title="StudyOS API")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=list(settings.allowed_origins),
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # ---------------------------------------------------------------------------
# # Response shapes — kept separate from the internal schemas.py models so the
# # API's public contract can stay stable even if internal fields change shape.
# # ---------------------------------------------------------------------------

# class LearnerSummary(BaseModel):
#     learner_id: str
#     has_curriculum: bool
#     goal_text: str | None = None
#     stages: list[dict] = []
#     current_concept_id: str | None = None
#     completed_concept_ids: list[str] = []


# class AnswerRequest(BaseModel):
#     answer: str


# def _summarize(state: LearnerState) -> LearnerSummary:
#     stages_out = []
#     if state.curriculum:
#         for stage in state.curriculum.stages:
#             mastery = state.concept_mastery.get(stage.concept_id)
#             stages_out.append(
#                 {
#                     "concept_id": stage.concept_id,
#                     "reason": stage.reason,
#                     "prerequisites": stage.prerequisites,
#                     "estimated_minutes": stage.estimated_minutes,
#                     "mastery": (mastery.mastery.value if mastery else MasteryLevel.NOT_STARTED.value),
#                     "primary_resource": stage.primary_resource.model_dump() if stage.primary_resource else None,
#                     "alternative_resources": [r.model_dump() for r in stage.alternative_resources],
#                     "reference_resources": [r.model_dump() for r in stage.reference_resources],
#                     "practice_resources": [r.model_dump() for r in stage.practice_resources],
#                     "is_current": stage.concept_id == state.current_concept_id,
#                 }
#             )
#     return LearnerSummary(
#         learner_id=state.learner_id,
#         has_curriculum=state.curriculum is not None,
#         goal_text=state.goal.raw_request if state.goal else None,
#         stages=stages_out,
#         current_concept_id=state.current_concept_id,
#         completed_concept_ids=state.completed_concept_ids,
#     )


# def _reconstruct_queue(state: LearnerState) -> list[str]:
#     if not state.curriculum:
#         return []
#     return [s.concept_id for s in state.curriculum.stages if s.concept_id not in state.completed_concept_ids]


# @app.get("/health")
# def health():
#     return {"ok": True}


# @app.get("/learners/{learner_id}", response_model=LearnerSummary)
# def get_learner(learner_id: str):
#     state = get_store().load_or_create(learner_id)
#     return _summarize(state)


# @app.get("/learners/{learner_id}/goal/stream")
# async def stream_goal(learner_id: str, raw_request: str):
#     """SSE endpoint. Runs the planning graph in a background thread (LangGraph's
#     .stream() is synchronous) and relays each node's new log lines to the
#     browser as they happen, then saves the final curriculum before closing.
#     """
#     q: Queue = Queue()
#     DONE = object()

#     def worker():
#         try:
#             graph = build_planning_graph()
#             final_state = None
#             for step in graph.stream(
#                 {"raw_request": raw_request, "learner_id": learner_id},
#                 stream_mode="values",
#             ):
#                 final_state = step
#                 for line in step.get("log", [])[_last_seen[0]:]:
#                     q.put(line)
#                 _last_seen[0] = len(step.get("log", []))

#             if final_state is None:
#                 q.put("__error__:planning produced no output")
#                 return

#             store = get_store()
#             learner_state = store.load_or_create(learner_id)
#             learner_state.goal = final_state["goal"]
#             learner_state.concept_graph = final_state["concept_graph"]
#             learner_state.curriculum = final_state["curriculum"]
#             store.save(learner_state)
#             q.put("__done__")
#         except Exception as e:  # noqa: BLE001 — surface any failure to the client, don't hang the stream
#             q.put(f"__error__:{e}")
#         finally:
#             q.put(DONE)

#     _last_seen = [0]
#     Thread(target=worker, daemon=True).start()

#     async def event_generator():
#         loop = asyncio.get_event_loop()
#         while True:
#             item = await loop.run_in_executor(None, _blocking_get, q)
#             if item is DONE:
#                 break
#             if item == "__done__":
#                 yield {"event": "done", "data": "curriculum ready"}
#             elif isinstance(item, str) and item.startswith("__error__:"):
#                 yield {"event": "error", "data": item[len("__error__:"):]}
#             else:
#                 yield {"event": "progress", "data": item}

#     return EventSourceResponse(event_generator())


# def _blocking_get(q: Queue):
#     return q.get()


# @app.get("/learners/{learner_id}/practice")
# def get_practice(learner_id: str):
#     store = get_store()
#     state = store.load_or_create(learner_id)
#     if not state.curriculum:
#         raise HTTPException(404, "No curriculum yet — generate one first.")

#     queue = _reconstruct_queue(state)
#     if not queue:
#         return {"done": True, "items": [], "results": []}

#     cid = queue[0]
#     state.current_concept_id = cid

#     if not state.active_practice_items or state.active_practice_items[0].concept_id != cid:
#         # Nothing in progress for this concept yet — generate and persist it.
#         progress_graph = build_progress_graph()
#         result = progress_graph.invoke(
#             {
#                 "concept_graph": state.concept_graph,
#                 "goal": state.goal,
#                 "stage_queue": queue,
#                 "learner_state": state,
#             }
#         )
#         state.active_practice_items = result["practice_items"]
#         state.active_results = []
#         store.save(state)

#     answered_ids = {r.practice_item_id for r in state.active_results}
#     return {
#         "done": False,
#         "concept_id": cid,
#         "items": [item.model_dump() for item in state.active_practice_items],
#         "answered_item_ids": list(answered_ids),
#         "results": [r.model_dump() for r in state.active_results],
#     }


# @app.post("/learners/{learner_id}/practice/{item_id}/answer")
# def submit_answer(learner_id: str, item_id: str, body: AnswerRequest):
#     store = get_store()
#     state = store.load_or_create(learner_id)
#     if not state.active_practice_items:
#         raise HTTPException(400, "No practice items in progress. Call GET .../practice first.")

#     item = next((i for i in state.active_practice_items if i.id == item_id), None)
#     if item is None:
#         raise HTTPException(404, f"No practice item with id {item_id} in the current session.")
#     if any(r.practice_item_id == item_id for r in state.active_results):
#         raise HTTPException(409, "This item was already graded.")

#     grading = grade_practice_item(item, body.answer)
#     result = AssessmentResult(
#         concept_id=item.concept_id,
#         practice_item_id=item.id,
#         score=grading.score,
#         feedback=grading.feedback,
#         weak_areas=grading.weak_areas,
#     )
#     # Save immediately — this is the per-answer persistence the frontend
#     # design relies on: closing the tab here loses nothing already graded.
#     state.active_results.append(result)
#     store.save(state)

#     all_answered = len(state.active_results) == len(state.active_practice_items)
#     response = {
#         "score": result.score,
#         "feedback": result.feedback,
#         "weak_areas": result.weak_areas,
#         "stage_complete": False,
#     }

#     if all_answered:
#         replan_graph = build_replan_graph()
#         replan_result = replan_graph.invoke(
#             {
#                 "current_concept_id": item.concept_id,
#                 "pending_results": state.active_results,
#                 "learner_state": state,
#                 "stage_queue": _reconstruct_queue(state),
#                 "log": [],
#             }
#         )
#         state = replan_result["learner_state"]
#         state.active_practice_items = []
#         state.active_results = []
#         store.save(state)

#         mastery = state.concept_mastery.get(item.concept_id)
#         response["stage_complete"] = True
#         response["mastery"] = mastery.mastery.value if mastery else None
#         response["advanced"] = item.concept_id in state.completed_concept_ids
#         response["curriculum_complete"] = len(_reconstruct_queue(state)) == 0

#     return response
