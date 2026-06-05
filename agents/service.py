"""
agents/service.py
─────────────────
TruthTellerService: Orchestrates the multi-agent graph execution.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from agents.graph import app
from agents.state import AgentState

log = logging.getLogger(__name__)

class TruthTellerService:
    """Service to handle listing verification requests."""

    @staticmethod
    def verify_listing(listing_text: str) -> Dict[str, Any]:
        """
        Executes the multi-agent graph for a given listing.

        Args:
            listing_text: The raw text description of the rental listing.

        Returns:
            The final state of the graph including resolved data and verdict.
        """
        log.info("Starting verification for new listing...")

        initial_state: AgentState = {
            "listing_input": listing_text,
            "address_resolved": None,
            "pricing_data": None,
            "vibe_data": None,
            "neighbourhood_data": None,
            "final_verdict": None,
            "messages": []
        }

        try:
            # Invoke the compiled LangGraph
            final_state = app.invoke(initial_state)
            log.info("Verification completed successfully.")
            return final_state
        except Exception as e:
            log.error(f"Error during graph execution: {e}")
            raise
