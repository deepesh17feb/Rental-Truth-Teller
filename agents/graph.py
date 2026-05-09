"""
agents/graph.py
───────────────
Assembles the multi-agent hierarchy using LangGraph.
Handles parallel execution branches (fan-out -> fan-in).
"""

from __future__ import annotations

import logging
from langgraph.graph import StateGraph, START, END

from agents.state import AgentState
from agents.supervisor import supervisor_node
from agents.pricing import pricing_node
from agents.vibe import vibe_check_node
from agents.neighbourhood import neighbourhood_node
from agents.synthesis import synthesis_node

log = logging.getLogger(__name__)

def build_truth_teller_graph() -> StateGraph:
    """Wires together the multi-agent StateGraph."""
    log.info("Assembling multi-agent LangGraph workflow…")
    
    # Initialize graph with standard AgentState
    workflow = StateGraph(AgentState)
    
    # 1. Register all workflow nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("pricing", pricing_node)
    workflow.add_node("vibe", vibe_check_node)
    workflow.add_node("neighbourhood", neighbourhood_node)
    workflow.add_node("synthesis", synthesis_node)
    
    # 2. Standard entrypoint edge
    workflow.add_edge(START, "supervisor")
    
    # 3. Fan-out: Route from Supervisor to parallel sub-agents
    # Because these nodes represent independent parallel streams, we draw direct
    # static edges from supervisor executing sequentially or concurrently into each.
    workflow.add_edge("supervisor", "pricing")
    workflow.add_edge("supervisor", "vibe")
    workflow.add_edge("supervisor", "neighbourhood")
    
    # 4. Fan-in: Sub-agents aggregate outcomes into the Synthesis Node
    workflow.add_edge("pricing", "synthesis")
    workflow.add_edge("vibe", "synthesis")
    workflow.add_edge("neighbourhood", "synthesis")
    
    # 5. Complete transition
    workflow.add_edge("synthesis", END)
    
    # Compile work graph
    compiled_graph = workflow.compile()
    log.info("LangGraph workflow successfully compiled.")
    return compiled_graph

# Shared static compilable object
app = build_truth_teller_graph()
