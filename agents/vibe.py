"""
agents/vibe.py
──────────────
Vibe Check Agent: Analyzes listing text, community signals, lifestyle constraints.
"""

from __future__ import annotations

import json
import logging
from langchain_core.prompts import ChatPromptTemplate
from agents.config import get_llm, get_response_text
from agents.state import AgentState, VibeAnalysis

log = logging.getLogger(__name__)

VIBE_CHECK_PROMPT = """You are the "Vibe Check Agent" in a rental verification network.
Given the user's raw property description or input listing, analyze the text to find:
1. Potential discrepancy red flags (e.g., listing claiming "next to metro" but mentioning "20 minutes walk").
2. Community signals (e.g., family-focused, nightlife, noise problems, security).
3. Lifestyle/diet/pet rules (e.g., "Only pure veg", "No pets", "Tenant type: bachelor boys only").
4. Overall sentiment profile of the listing (e.g. Enthusiastic, Pressuring, Deceptive, Warm).

Raw Listing Input:
{listing_input}

Return a strictly formatted JSON object matching this schema:
{{
  "amenity_vs_claim_diffs": ["list of found discrepancies or exaggerations"],
  "community_signals": ["extracted vibe/neighbourhood feel signals from text"],
  "diet_pet_lifestyle": ["restrictive rules like food, pets, gender, marital status constraints"],
  "listing_nlp_sentiment": "One word describing overall listing sentiment"
}}
Ensure you return ONLY the raw JSON structure. Do not enclose it in markdown tables, wrappers or backticks.
"""

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
        
        # Handle raw prompt response cleaning
        content = get_response_text(response)
        if content.startswith("```json"):
            content = content.replace("```json", "", 1)
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        data = json.loads(content)
        
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
        # Return fallback VibeAnalysis
        return {
            "vibe_data": VibeAnalysis(
                amenity_vs_claim_diffs=["Unable to perform description NLP validation due to exception."],
                community_signals=[],
                diet_pet_lifestyle=[],
                listing_nlp_sentiment="Error"
            ),
            "messages": [f"[Vibe Check Agent] Error encountered: {str(e)}"]
        }
