"""Runs the planning graph over a diverse set of learning goals and reports
structural + LLM-judge metrics for each.

    python eval/run_eval.py

Requires GROQ_API_KEY (real LLM calls, real cost — this is not free to
run, unlike the pytest suite which mocks the LLM entirely). Writes a JSON
report to eval/results/.

What this does and doesn't tell you: it tells you whether the pipeline
produces structurally valid, plausible-looking curricula across a variety of
subjects without hardcoded per-subject logic. It does NOT tell you whether
the actual recommended resources are good — that requires either a human
opening the links, or a separate harness that fetches resource content and
checks it against the concept (not implemented here; a reasonable next
step).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from metrics import llm_judge_metrics, structural_metrics  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from studyos.graph.build_graph import build_planning_graph  # noqa: E402

console = Console()


def run_eval(goals_path: str = "eval/eval_goals.json") -> list[dict]:
    goals = json.loads(Path(goals_path).read_text())
    graph = build_planning_graph()
    results = []

    for g in goals:
        console.print(f"[bold]Running:[/bold] {g['id']}")
        try:
            state = graph.invoke({"raw_request": g["raw_request"], "learner_id": f"eval-{g['id']}"})
            curriculum = state["curriculum"]
            structural = structural_metrics(curriculum)
            judge = llm_judge_metrics(curriculum)
            results.append({"id": g["id"], "ok": True, "structural": structural, "judge": judge})
        except Exception as e:
            console.print(f"[red]  failed: {e}[/red]")
            results.append({"id": g["id"], "ok": False, "error": str(e)})

    return results


def print_summary(results: list[dict]) -> None:
    table = Table(title="StudyOS Evaluation")
    table.add_column("Goal")
    table.add_column("OK")
    table.add_column("Stages")
    table.add_column("Order violations")
    table.add_column("URL validity")
    table.add_column("Judge: relevance")
    table.add_column("Judge: depth fit")

    for r in results:
        if not r["ok"]:
            table.add_row(r["id"], "FAIL", "-", "-", "-", "-", "-")
            continue
        s, j = r["structural"], r["judge"]
        table.add_row(
            r["id"],
            "ok",
            str(s["num_stages"]),
            str(s["prerequisite_order_violations"]),
            f"{s['resource_url_validity_rate']:.0%}" if s["resource_url_validity_rate"] is not None else "n/a",
            f"{j['curriculum_relevance_to_goal']:.1f}/5",
            f"{j['appropriate_depth_for_target_level']:.1f}/5",
        )
    console.print(table)


if __name__ == "__main__":
    results = run_eval()
    print_summary(results)

    out_dir = Path("eval/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(results, indent=2))
    console.print(f"\nSaved: {out_path}")
