import pytest

from studyos.schemas import Concept, ConceptGraph


def _graph(edges: dict[str, list[str]]) -> ConceptGraph:
    concepts = {
        cid: Concept(id=cid, name=cid, description="", depends_on=deps)
        for cid, deps in edges.items()
    }
    return ConceptGraph(concepts=concepts)


def test_topological_order_respects_dependencies():
    g = _graph({
        "a": [],
        "b": ["a"],
        "c": ["a", "b"],
    })
    order = g.topological_order()
    assert order.index("a") < order.index("b") < order.index("c")


def test_topological_order_is_deterministic():
    g = _graph({"x": [], "a": [], "m": []})
    assert g.topological_order() == ["a", "m", "x"]


def test_cycle_raises():
    g = _graph({"a": ["b"], "b": ["a"]})
    with pytest.raises(ValueError, match="Cycle"):
        g.topological_order()


def test_single_node_no_deps():
    g = _graph({"a": []})
    assert g.topological_order() == ["a"]
