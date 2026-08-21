# agents/graph.py
"""
agents/graph.py
───────────────
Assembles the multi-agent hierarchy using LangGraph.
Handles parallel execution branches (fan-out -> fan-in):
Supervisor -> {Pricing, Vibe, Neighbourhood} (parallel) -> Synthesis.
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.supervisor import supervisor_node
from agents.pricing import pricing_node
from agents.vibe import vibe_check_node
from agents.neighbourhood import neighbourhood_node
from agents.synthesis import synthesis_node

log = logging.getLogger(__name__)


def build_truth_teller_graph():
    """Builds and compiles the LangGraph StateGraph with a real
    fan-out/fan-in workflow: Supervisor resolves the address, then
    Pricing/Vibe/Neighbourhood run concurrently off that shared state,
    and Synthesis waits for all three before compiling the verdict."""
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("pricing", pricing_node)
    graph.add_node("vibe", vibe_check_node)
    graph.add_node("neighbourhood", neighbourhood_node)
    graph.add_node("synthesis", synthesis_node)

    graph.set_entry_point("supervisor")

    graph.add_edge("supervisor", "pricing")
    graph.add_edge("supervisor", "vibe")
    graph.add_edge("supervisor", "neighbourhood")

    graph.add_edge("pricing", "synthesis")
    graph.add_edge("vibe", "synthesis")
    graph.add_edge("neighbourhood", "synthesis")

    graph.add_edge("synthesis", END)

    return graph.compile()


# Shared compiled graph object
app = build_truth_teller_graph()
