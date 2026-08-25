# tests/test_graph.py
import time

from agents.graph import build_truth_teller_graph
from agents.state import AgentState


def _initial_state(listing_input: str = "test listing") -> AgentState:
    return {
        "listing_input": listing_input,
        "address_resolved": None,
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def _slow_node(key: str, sleep_s: float):
    def node(state):
        time.sleep(sleep_s)
        return {key: f"{key}-result", "messages": [f"{key} done"]}
    return node


def test_pricing_vibe_neighbourhood_run_in_parallel(monkeypatch):
    monkeypatch.setattr(
        "agents.graph.supervisor_node",
        lambda state: {"address_resolved": None, "messages": ["supervisor done"]},
    )
    monkeypatch.setattr("agents.graph.pricing_node", _slow_node("pricing_data", 0.3))
    monkeypatch.setattr("agents.graph.vibe_check_node", _slow_node("vibe_data", 0.3))
    monkeypatch.setattr("agents.graph.neighbourhood_node", _slow_node("neighbourhood_data", 0.3))
    monkeypatch.setattr(
        "agents.graph.synthesis_node",
        lambda state: {"final_verdict": "verdict-result", "messages": ["synthesis done"]},
    )

    graph = build_truth_teller_graph()

    start = time.time()
    result = graph.invoke(_initial_state())
    elapsed = time.time() - start

    # Sequential would take >= 0.9s (3 * 0.3s); parallel should take ~0.3-0.5s.
    assert elapsed < 0.7, f"expected parallel execution, took {elapsed:.2f}s"
    assert result["pricing_data"] == "pricing_data-result"
    assert result["vibe_data"] == "vibe_data-result"
    assert result["neighbourhood_data"] == "neighbourhood_data-result"
    assert result["final_verdict"] == "verdict-result"


def test_full_graph_path_with_mocked_nodes(monkeypatch):
    monkeypatch.setattr(
        "agents.graph.supervisor_node",
        lambda state: {"address_resolved": "addr", "messages": ["supervisor done"]},
    )
    monkeypatch.setattr(
        "agents.graph.pricing_node",
        lambda state: {"pricing_data": "pricing", "messages": ["pricing done"]},
    )
    monkeypatch.setattr(
        "agents.graph.vibe_check_node",
        lambda state: {"vibe_data": "vibe", "messages": ["vibe done"]},
    )
    monkeypatch.setattr(
        "agents.graph.neighbourhood_node",
        lambda state: {"neighbourhood_data": "neigh", "messages": ["neigh done"]},
    )
    monkeypatch.setattr(
        "agents.graph.synthesis_node",
        lambda state: {"final_verdict": "verdict", "messages": ["synthesis done"]},
    )

    graph = build_truth_teller_graph()
    result = graph.invoke(_initial_state())

    assert result["address_resolved"] == "addr"
    assert result["pricing_data"] == "pricing"
    assert result["vibe_data"] == "vibe"
    assert result["neighbourhood_data"] == "neigh"
    assert result["final_verdict"] == "verdict"
    assert "supervisor done" in result["messages"]
    assert "synthesis done" in result["messages"]
