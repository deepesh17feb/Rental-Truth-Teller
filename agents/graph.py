"""
agents/graph.py
───────────────
Assembles the multi-agent hierarchy using LangGraph.
Handles parallel execution branches (fan-out -> fan-in).
"""

from __future__ import annotations

import logging

from agents.state import AgentState
from agents.supervisor import supervisor_node
from agents.pricing import pricing_node
from agents.vibe import vibe_check_node
from agents.neighbourhood import neighbourhood_node
from agents.synthesis import synthesis_node
log = logging.getLogger(__name__)

def build_truth_teller_graph():
    """Executes the multi-agent workflow sequentially."""
    
    def invoke(state: AgentState) -> dict:
        log.info("Executing multi-agent workflow sequentially…")
        
        # 1. Supervisor
        supervisor_res = supervisor_node(state)
        state.update(supervisor_res)
        
        # 2. Parallel Sub-agents (executed sequentially for simplicity)
        pricing_res = pricing_node(state)
        state.update(pricing_res)
        
        vibe_res = vibe_check_node(state)
        state.update(vibe_res)
        
        neigh_res = neighbourhood_node(state)
        state.update(neigh_res)
        
        # 3. Synthesis
        synthesis_res = synthesis_node(state)
        state.update(synthesis_res)
        
        log.info("Workflow successfully completed.")
        return state
        
    class SequentialGraph:
        def invoke(self, state: dict) -> dict:
            return invoke(state)
            
    return SequentialGraph()

# Shared static compilable object
app = build_truth_teller_graph()
