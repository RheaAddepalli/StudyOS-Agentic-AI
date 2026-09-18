"""Command-line runner.

    python -m studyos.cli --learner rhea --path transformers "I want to learn \
    Transformers from the fundamentals, I know Python and basic neural nets, \
    1 hour/day."

A learner can have several independent paths going at once (e.g. "python"
and "transformers") — `--path` picks which one this run operates on,
defaulting to "default" if you don't care about running more than one.

Behavior:
- If this path doesn't exist yet for this learner, runs the one-shot
  planning graph (goal_understanding -> ... -> curriculum_planning) and
  saves it as a new path.
- If the path already has a curriculum (resumed run), skips straight to
  wherever it left off using stage_queue reconstructed from
  completed_concept_ids — this is the "survive application restarts"
  requirement in practice.
- Then loops: generate practice for the current concept, ask the learner for
  answers, grade them, update mastery, decide whether to advance or
  remediate, save state after every step.
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .graph.build_graph import build_planning_graph, build_progress_graph, build_replan_graph
from .graph.nodes import grade_practice_item
from .schemas import AssessmentResult, LearningPath, PracticeItemType
from .state import StateStore

console = Console()


def _print_log(state: dict) -> None:
    for line in state.get("log", []):
        console.print(f"[dim]{line}[/dim]")


def _print_curriculum(curriculum) -> None:
    for i, stage in enumerate(curriculum.stages, 1):
        console.print(f"\n[bold cyan]{i}. {stage.concept_id}[/bold cyan]  (~{stage.estimated_minutes} min)")
        console.print(f"   why: {stage.reason}")
        if stage.primary_resource:
            r = stage.primary_resource
            console.print(f"   primary: [link={r.url}]{r.title}[/link]  — {r.justification}")
        for alt in stage.alternative_resources:
            console.print(f"   alt: [link={alt.url}]{alt.title}[/link]")
        for ref in stage.reference_resources:
            console.print(f"   ref: [link={ref.url}]{ref.title}[/link]")


def _reconstruct_queue(path: LearningPath) -> list[str]:
    if not path.curriculum:
        return []
    return [s.concept_id for s in path.curriculum.stages if s.concept_id not in path.completed_concept_ids]


def run(learner_id: str, path_name: str, raw_request: str | None) -> None:
    store = StateStore()
    learner_state = store.load_or_create(learner_id)
    path = learner_state.paths.get(path_name)

    if path is None:
        if not raw_request:
            console.print(
                f"[red]No path named '{path_name}' for '{learner_id}' yet, and no goal text given.[/red]"
            )
            sys.exit(1)

        console.print(Panel(f"Learning Goal ({path_name})\n{raw_request}", title="StudyOS"))
        planning_graph = build_planning_graph()
        result = planning_graph.invoke({"raw_request": raw_request, "learner_id": learner_id})
        _print_log(result)
        _print_curriculum(result["curriculum"])

        path = LearningPath(
            path_name=path_name,
            goal=result["goal"],
            concept_graph=result["concept_graph"],
            curriculum=result["curriculum"],
        )
        learner_state.paths[path_name] = path
        store.save(learner_state)
    else:
        console.print(f"[green]Resuming '{path_name}' for '{learner_id}'.[/green]")
        _print_curriculum(path.curriculum)

    stage_queue = _reconstruct_queue(path)
    if not stage_queue:
        console.print(f"\n[bold green]All concepts completed for '{path_name}'.[/bold green]")
        return

    progress_graph = build_progress_graph()
    replan_graph = build_replan_graph()

    while stage_queue:
        cid = stage_queue[0]
        console.print(f"\n[bold]--- {cid} ---[/bold]")

        gen_result = progress_graph.invoke(
            {
                "concept_graph": path.concept_graph,
                "goal": path.goal,
                "stage_queue": stage_queue,
                "learner_state": path,
            }
        )
        items = gen_result["practice_items"]

        results: list[AssessmentResult] = []
        for item in items:
            console.print(Panel(Markdown(item.prompt), title=f"{item.type.value}"))
            if item.starter_code:
                console.print(Markdown(f"```python\n{item.starter_code}\n```"))
            answer = console.input("[yellow]Your answer (or code):[/yellow]\n")
            grading = grade_practice_item(item, answer)
            console.print(f"  score: {grading.score}/10 — {grading.feedback}")
            results.append(
                AssessmentResult(
                    concept_id=cid,
                    practice_item_id=item.id,
                    score=grading.score,
                    feedback=grading.feedback,
                    weak_areas=grading.weak_areas,
                )
            )

        replan_result = replan_graph.invoke(
            {
                "current_concept_id": cid,
                "pending_results": results,
                "learner_state": path,
                "stage_queue": stage_queue,
                "log": [],
            }
        )
        _print_log(replan_result)
        path = replan_result["learner_state"]
        stage_queue = replan_result["stage_queue"]
        learner_state.paths[path_name] = path
        store.save(learner_state)  # persist after every concept, not just at the end

    console.print(f"\n[bold green]'{path_name}' complete.[/bold green]")


def main():
    parser = argparse.ArgumentParser(description="StudyOS — adaptive learning agent")
    parser.add_argument("goal", nargs="?", help="Free-text learning goal (only needed for a new path)")
    parser.add_argument("--learner", required=True, help="Learner id, used to load/save persistent state")
    parser.add_argument(
        "--path", default="default", help="Which learning path this run operates on (default: 'default')"
    )
    args = parser.parse_args()
    run(args.learner, args.path, args.goal)


if __name__ == "__main__":
    main()




















# """Command-line runner.

#     python -m studyos.cli --learner rhea "I want to learn Transformers from
#     the fundamentals, I know Python and basic neural nets, 1 hour/day."

# Behavior:
# - If the learner has no saved curriculum for this goal, runs the one-shot
#   planning graph (goal_understanding -> ... -> curriculum_planning) and
#   saves it.
# - If the learner already has a curriculum (resumed run), skips straight to
#   wherever they left off using stage_queue reconstructed from
#   completed_concept_ids — this is the "survive application restarts"
#   requirement in practice.
# - Then loops: generate practice for the current concept, ask the learner for
#   answers, grade them, update mastery, decide whether to advance or
#   remediate, save state after every step.
# """

# from __future__ import annotations

# import argparse
# import sys

# from rich.console import Console
# from rich.markdown import Markdown
# from rich.panel import Panel

# from .graph.build_graph import build_planning_graph, build_progress_graph, build_replan_graph
# from .graph.nodes import grade_practice_item
# from .schemas import AssessmentResult, LearnerState, PracticeItemType
# from .state import StateStore

# console = Console()


# def _print_log(state: dict) -> None:
#     for line in state.get("log", []):
#         console.print(f"[dim]{line}[/dim]")


# def _print_curriculum(curriculum) -> None:
#     for i, stage in enumerate(curriculum.stages, 1):
#         console.print(f"\n[bold cyan]{i}. {stage.concept_id}[/bold cyan]  (~{stage.estimated_minutes} min)")
#         console.print(f"   why: {stage.reason}")
#         if stage.primary_resource:
#             r = stage.primary_resource
#             console.print(f"   primary: [link={r.url}]{r.title}[/link]  — {r.justification}")
#         for alt in stage.alternative_resources:
#             console.print(f"   alt: [link={alt.url}]{alt.title}[/link]")
#         for ref in stage.reference_resources:
#             console.print(f"   ref: [link={ref.url}]{ref.title}[/link]")


# def _reconstruct_queue(learner_state: LearnerState) -> list[str]:
#     if not learner_state.curriculum:
#         return []
#     return [
#         s.concept_id
#         for s in learner_state.curriculum.stages
#         if s.concept_id not in learner_state.completed_concept_ids
#     ]


# def run(learner_id: str, raw_request: str | None) -> None:
#     store = StateStore()
#     learner_state = store.load_or_create(learner_id)

#     if learner_state.curriculum is None:
#         if not raw_request:
#             console.print("[red]No saved curriculum for this learner and no goal text given.[/red]")
#             sys.exit(1)

#         console.print(Panel(f"Learning Goal\n{raw_request}", title="StudyOS"))
#         planning_graph = build_planning_graph()
#         result = planning_graph.invoke({"raw_request": raw_request, "learner_id": learner_id})
#         _print_log(result)
#         _print_curriculum(result["curriculum"])

#         learner_state.goal = result["goal"]
#         learner_state.concept_graph = result["concept_graph"]
#         learner_state.curriculum = result["curriculum"]
#         store.save(learner_state)
#     else:
#         console.print(f"[green]Resuming saved curriculum for '{learner_id}'.[/green]")
#         _print_curriculum(learner_state.curriculum)

#     stage_queue = _reconstruct_queue(learner_state)
#     if not stage_queue:
#         console.print("\n[bold green]All concepts completed for this goal.[/bold green]")
#         return

#     progress_graph = build_progress_graph()
#     replan_graph = build_replan_graph()

#     while stage_queue:
#         cid = stage_queue[0]
#         console.print(f"\n[bold]--- {cid} ---[/bold]")

#         gen_result = progress_graph.invoke(
#             {
#                 "concept_graph": learner_state.concept_graph,
#                 "goal": learner_state.goal,
#                 "stage_queue": stage_queue,
#                 "learner_state": learner_state,
#             }
#         )
#         items = gen_result["practice_items"]

#         results: list[AssessmentResult] = []
#         for item in items:
#             console.print(Panel(Markdown(item.prompt), title=f"{item.type.value}"))
#             if item.starter_code:
#                 console.print(Markdown(f"```python\n{item.starter_code}\n```"))
#             answer = console.input("[yellow]Your answer (or code):[/yellow]\n")
#             grading = grade_practice_item(item, answer)
#             console.print(f"  score: {grading.score}/10 — {grading.feedback}")
#             results.append(
#                 AssessmentResult(
#                     concept_id=cid,
#                     practice_item_id=item.id,
#                     score=grading.score,
#                     feedback=grading.feedback,
#                     weak_areas=grading.weak_areas,
#                 )
#             )

#         replan_result = replan_graph.invoke(
#             {
#                 "current_concept_id": cid,
#                 "pending_results": results,
#                 "learner_state": learner_state,
#                 "stage_queue": stage_queue,
#                 "log": [],
#             }
#         )
#         _print_log(replan_result)
#         learner_state = replan_result["learner_state"]
#         stage_queue = replan_result["stage_queue"]
#         store.save(learner_state)  # persist after every concept, not just at the end

#     console.print("\n[bold green]Curriculum complete.[/bold green]")


# def main():
#     parser = argparse.ArgumentParser(description="StudyOS — adaptive learning agent")
#     parser.add_argument("goal", nargs="?", help="Free-text learning goal (only needed for a new curriculum)")
#     parser.add_argument("--learner", required=True, help="Learner id, used to load/save persistent state")
#     args = parser.parse_args()
#     run(args.learner, args.goal)


# if __name__ == "__main__":
#     main()
