"""
agents/synthesis.py
───────────────────
Synthesis Agent: Collates results from Vibe, Pricing, and Neighbourhood sub-agents 
to compile the final Verdict Card and custom broker questionnaire.
"""

from __future__ import annotations

import json
import logging
from langchain_core.prompts import ChatPromptTemplate
from agents.config import get_llm, rerank_listings
from agents.state import AgentState, VerdictCard

log = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """You are the "Synthesis Agent" in a rental validation multi-agent network.
Collect all preceding sub-agent analyses and synthesize them into a consolidated "Verdict Card" report.

Context data:
- Address Resolved: {address_resolved}
- Price Analysis: {pricing_data}
- Vibe & Rules: {vibe_data}
- Neighborhood & Metro proximity: {neighbourhood_data}

Output parameters required:
1. Overpriced Percentage: directly mapped or adjusted from Price Analysis.
2. Red Flags list: Gather extreme prices, strict lease terms (e.g. high deposit, bachelors penalty, veg-only restrictions) or POI deficiencies (e.g. no metro within 3km).
3. Broker Questionnaire: 4 key critical/clever questions to ask the broker or owner based on discrepancies OR constraints identified here.
4. Fair Range: Return a dynamic estimates minimum and maximum rate (e.g., average rent +/- 10%).
5. Neighbourhood Score: Compute a score from 0 to 10 based on POIs (Metro < 1.5km adds 4 pts, School > 0 adds 2 pts, Hospital > 0 adds 2 pts, Market > 0 adds 2 pts).

Return a strictly formatted JSON object matching this schema:
{{
  "fair_range_min": 32000.0,
  "fair_range_max": 38000.0,
  "overpriced_percentage": 12.5,
  "red_flags": ["example flag 1", "example flag 2"],
  "neighbourhood_score": 8.0,
  "broker_questionnaire": ["question 1", "question 2"]
}}
Provide ONLY the raw JSON response.
"""

def synthesis_node(state: AgentState) -> dict:
    log.info("[Synthesis Agent] Constructing final Verdict Card & Reranking comparables…")
    
    address_resolved = state.get("address_resolved")
    pricing_data = state.get("pricing_data")
    vibe_data = state.get("vibe_data")
    neighbourhood_data = state.get("neighbourhood_data")
    
    # 1. Execute Jina Rerank on fallback comparables to isolate top comparables (For log demonstration)
    query = f"Rental apartment in {address_resolved.locality if address_resolved else 'Bangalore'}"
    dummy_comparables = [
        {"title": "Cozy 2BHK in Whitefield", "description": "Fully furnished close to tech parks", "address": "Whitefield Main Road"},
        {"title": "Premium 3BHK Koramangala", "description": "High rent, premium styling, next to eateries", "address": "Koramangala 4th Block"},
        {"title": "Affordable HSR Layout 1BHK", "description": "Spacious apartment, perfect for bachelors", "address": "HSR Layout Sector 2"}
    ]
    top_comparables = rerank_listings(query, dummy_comparables, top_k=2)
    log.info(f"[Synthesis Agent] Reranked comparables: {[c.get('title') for c in top_comparables]}")

    # 2. Synthesize using Bedrock LLM
    llm = get_llm(temperature=0.1)
    prompt = ChatPromptTemplate.from_template(SYNTHESIS_PROMPT)
    chain = prompt | llm

    # 3. Upfront Cost Calculations:
    # Bangalore standard upfront = Monthly Rent + Security Deposit + standard cleaning/brokerage (default 1 month rent)
    rent = pricing_data.rent_amount if pricing_data else 0.0
    deposit = pricing_data.deposit_amount if pricing_data else 0.0
    brokerage_and_paint = rent  # Assume 1-month rent for standard fees in Bangalore
    total_upfront_cost = rent + deposit + brokerage_and_paint

    try:
        response = chain.invoke({
            "address_resolved": address_resolved.model_dump() if address_resolved else {},
            "pricing_data": pricing_data.model_dump() if pricing_data else {},
            "vibe_data": vibe_data.model_dump() if vibe_data else {},
            "neighbourhood_data": neighbourhood_data.model_dump() if neighbourhood_data else {},
        })
        
        content = response.content.strip()
        if content.startswith("```json"):
            content = content.replace("```json", "", 1)
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        data = json.loads(content)
        
        verdict = VerdictCard(
            fair_range_min=data.get("fair_range_min", rent * 0.9),
            fair_range_max=data.get("fair_range_max", rent * 1.1),
            overpriced_percentage=data.get("overpriced_percentage", pricing_data.overpriced_percentage if pricing_data else 0.0),
            total_upfront_cost=total_upfront_cost,
            red_flags=data.get("red_flags", []),
            neighbourhood_score=data.get("neighbourhood_score", 5.0),
            broker_questionnaire=data.get("broker_questionnaire", [])
        )
        
        # Proactively check for any additional price drift flag or deposit anomaly flag
        if pricing_data:
            if pricing_data.price_drift_flag and "High price variance detected (above local average)" not in verdict.red_flags:
                verdict.red_flags.append("Property pricing is majorly drifted from local comparable averages.")
            if not pricing_data.deposit_is_normal and "Deceptive deposit expectation (>10 months landlord deposit)" not in verdict.red_flags:
                verdict.red_flags.append(f"Security deposit demands are high ({pricing_data.deposit_multiplier}x rent).")
                
        log.info("[Synthesis Agent] Final Verdict Card generated.")
        return {
            "final_verdict": verdict,
            "messages": ["[Synthesis Agent] Compiled all reports into a finalized Verdict Card with custom broker questionnaire."]
        }
        
    except Exception as e:
        log.error(f"[Synthesis Agent] Error executing synthesis LLM: {e}")
        # Simple fallback
        flat_verdict = VerdictCard(
            fair_range_min=rent * 0.85,
            fair_range_max=rent * 1.15,
            overpriced_percentage=pricing_data.overpriced_percentage if pricing_data else 0.0,
            total_upfront_cost=total_upfront_cost,
            red_flags=["Failed to run composite synthesis, showing structural pricing alerts only."],
            neighbourhood_score=6.0,
            broker_questionnaire=["Why does the landlord charge this amount of rent?"]
        )
        return {
            "final_verdict": flat_verdict,
            "messages": [f"[Synthesis Agent] Synthesis error fallback: {str(e)}"]
        }
