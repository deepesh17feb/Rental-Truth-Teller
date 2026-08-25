"""
agents/vibe.py
──────────────
Vibe Check Agent: Analyzes listing text, community signals, lifestyle constraints.
"""

from __future__ import annotations

import logging
from agents.config import get_llm
from agents.prompts import VIBE_CHECK_PROMPT
from agents.state import AgentState, VibeAnalysis
from agents.fallbacks import fallback_vibe_analysis
from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import VibeResult

log = logging.getLogger(__name__)

def vibe_check_node(state: AgentState) -> dict:
    """Analyze the listing for claims vs truth differences, tenant rules and vibes."""
    log.info("[Vibe Check Agent] Processing Listing Text…")

    listing_input = state.get("listing_input", "")
    if not listing_input:
        return {"vibe_data": VibeAnalysis()}

    llm = get_llm(temperature=0.1)

    try:
        data = call_llm_structured(llm, VIBE_CHECK_PROMPT, {"listing_input": listing_input}, VibeResult)

        vibe_res = VibeAnalysis(
            amenity_vs_claim_diffs=data.amenity_vs_claim_diffs,
            community_signals=data.community_signals,
            diet_pet_lifestyle=data.diet_pet_lifestyle,
            listing_nlp_sentiment=data.listing_nlp_sentiment
        )

        log.info(f"[Vibe Check Agent] Success. Sentiment: {vibe_res.listing_nlp_sentiment}")
        return {"vibe_data": vibe_res, "messages": ["[Vibe Check Agent] Successfully parsed listing description & rules."]}

    except LLMCallError as e:
        log.error(f"[Vibe Check Agent] Error executing vibe checker LLM: {e}")
        return fallback_vibe_analysis(str(e))
