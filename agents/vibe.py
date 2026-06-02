"""
agents/vibe.py
──────────────
Vibe Check Agent: Analyzes listing text, community signals, lifestyle constraints.
"""

from __future__ import annotations

import logging
from langchain_core.prompts import ChatPromptTemplate
from agents.config import get_llm, get_response_text
from agents.prompts import VIBE_CHECK_PROMPT
from agents.state import AgentState, VibeAnalysis
from agents.fallbacks import fallback_vibe_analysis
from agents.utils import parse_json_from_llm

log = logging.getLogger(__name__)

def vibe_check_node(state: AgentState) -> dict:
    """Analyze the listing for claims vs truth differences, tenant rules and vibes."""
    log.info("[Vibe Check Agent] Processing Listing Text…")
    
    listing_input = state.get("listing_input", "")
    if not listing_input:
        return {"vibe_data": VibeAnalysis()}

    llm = get_llm(temperature=0.1)
    prompt = ChatPromptTemplate.from_template(VIBE_CHECK_PROMPT)
    chain = prompt | llm

    try:
        response = chain.invoke({"listing_input": listing_input})
        
        content = get_response_text(response)
        data = parse_json_from_llm(content)
        
        vibe_res = VibeAnalysis(
            amenity_vs_claim_diffs=data.get("amenity_vs_claim_diffs", []),
            community_signals=data.get("community_signals", []),
            diet_pet_lifestyle=data.get("diet_pet_lifestyle", []),
            listing_nlp_sentiment=data.get("listing_nlp_sentiment", "Neutral")
        )
        
        log.info(f"[Vibe Check Agent] Success. Sentiment: {vibe_res.listing_nlp_sentiment}")
        return {"vibe_data": vibe_res, "messages": ["[Vibe Check Agent] Successfully parsed listing description & rules."]}
    
    except Exception as e:
        log.error(f"[Vibe Check Agent] Error executing vibe checker LLM: {e}")
        return fallback_vibe_analysis(str(e))
