"""Real MCP server exposing StudyOS's tools over the Model Context Protocol.

Architecture note (why this exists alongside direct Python calls in
graph/nodes.py): the LangGraph pipeline calls web_search/arxiv_search/etc.
as plain in-process functions for latency and error-handling simplicity —
routing every internal tool call through an MCP round-trip would add
latency for no benefit when the caller and the tool live in the same
process. This server exposes the *same* underlying tools over MCP so that
external MCP clients — Claude Desktop, another agent, a different
orchestrator — can drive StudyOS's research and state capabilities without
importing its Python package. Run it with:

    python -m studyos.mcp_server

and point any MCP client at it over stdio.
"""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from .schemas import LearnerState
from .state import StateStore
from .tools import arxiv_search, github_search, run_python, web_search

mcp = MCPServer("studyos")
_store = StateStore()


@mcp.tool()
def search_web(query: str, max_results: int = 6) -> str:
    """Search the general web for tutorials, docs, and explanations on a topic."""
    return json.dumps(web_search(query, max_results))


@mcp.tool()
def search_papers(query: str, max_results: int = 5) -> str:
    """Search arXiv for research papers relevant to a concept or topic."""
    return json.dumps(arxiv_search(query, max_results))


@mcp.tool()
def search_github(query: str, max_results: int = 5) -> str:
    """Search GitHub repositories for implementations or reference code."""
    return json.dumps(github_search(query, max_results))


@mcp.tool()
def execute_python(code: str, stdin: str = "") -> str:
    """Run learner-submitted Python in a sandboxed subprocess and return
    stdout/stderr/exit_code. Timeout and memory limited; see tools/code_exec.py
    for the exact guarantees and non-guarantees."""
    result = run_python(code, stdin)
    return json.dumps(
        {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
        }
    )


@mcp.tool()
def get_learner_state(learner_id: str) -> str:
    """Fetch the persisted learning state for a learner: goal, curriculum
    progress, mastery per concept, completed concepts."""
    state = _store.load(learner_id)
    if state is None:
        return json.dumps({"error": f"no state found for learner_id={learner_id}"})
    return state.model_dump_json(indent=2)


@mcp.tool()
def save_learner_state(learner_id: str, state_json: str) -> str:
    """Persist a learner's state (must be a valid LearnerState JSON object)."""
    state = LearnerState.model_validate_json(state_json)
    state.learner_id = learner_id
    _store.save(state)
    return json.dumps({"ok": True, "learner_id": learner_id})


if __name__ == "__main__":
    mcp.run(transport="stdio")
