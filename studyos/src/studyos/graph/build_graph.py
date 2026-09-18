"""Builds the LangGraph StateGraph.

Pipeline shape:

    goal_understanding -> prerequisite_reasoning -> research
        -> resource_evaluation -> curriculum_planning
        -> practice_generation --[assessment happens outside the graph,
                                    see cli.py]--> progress_tracking_and_replan
                                                        |
                                    continue (next/remediate) --back to practice_generation
                                    complete -----------> END

Assessment is deliberately NOT a graph node. Grading requires an interactive
learner answer for each practice item, which doesn't fit a single
non-interactive node invocation. `practice_generation` and
`progress_tracking_and_replan` are the two graph nodes either side of it;
`cli.py` drives the interactive part and calls `grade_practice_item` per
answer before invoking the graph again for the next step. This keeps the
graph itself synchronous and testable while the interactive loop lives where
interactivity belongs.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from . import nodes
from .state import GraphState


def build_planning_graph():
    """The one-shot pipeline: goal -> curriculum. Run once per new learning goal."""
    graph = StateGraph(GraphState)
    graph.add_node("goal_understanding", nodes.goal_understanding)
    graph.add_node("prerequisite_reasoning", nodes.prerequisite_reasoning)
    graph.add_node("research", nodes.research)
    graph.add_node("resource_evaluation", nodes.resource_evaluation)
    graph.add_node("curriculum_planning", nodes.curriculum_planning)

    graph.set_entry_point("goal_understanding")
    graph.add_edge("goal_understanding", "prerequisite_reasoning")
    graph.add_edge("prerequisite_reasoning", "research")
    graph.add_edge("research", "resource_evaluation")
    graph.add_edge("resource_evaluation", "curriculum_planning")
    graph.add_edge("curriculum_planning", END)
    return graph.compile()


def build_progress_graph():
    """The repeating step: generate practice for the current concept. Called
    once to get practice items, then again (after grading, outside the graph)
    to advance or remediate."""
    graph = StateGraph(GraphState)
    graph.add_node("practice_generation", nodes.practice_generation)
    graph.set_entry_point("practice_generation")
    graph.add_edge("practice_generation", END)
    return graph.compile()


def build_replan_graph():
    graph = StateGraph(GraphState)
    graph.add_node("progress_tracking_and_replan", nodes.progress_tracking_and_replan)
    graph.set_entry_point("progress_tracking_and_replan")
    graph.add_edge("progress_tracking_and_replan", END)
    return graph.compile()
