# agents/synthesis.py
"""
agents/synthesis.py
───────────────────
Synthesis Agent: Collates results from Vibe, Pricing, and Neighbourhood sub-agents
to compile the final Verdict Card and custom broker questionnaire.
"""

from __future__ import annotations

import logging
from agents.config import get_llm
from agents.prompts import SYNTHESIS_PROMPT
from agents.state import AgentState, VerdictCard
from agents.fallbacks import fallback_synthesis
from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import SynthesisResult

log = logging.getLogger(__name__)

def synthesis_node(state: AgentState) -> dict:
    log.info("[Synthesis Agent] Constructing final Verdict Card…")

    address_resolved = state.get("address_resolved")
    pricing_data = state.get("pricing_data")
    vibe_data = state.get("vibe_data")
    neighbourhood_data = state.get("neighbourhood_data")

    llm = get_llm(temperature=0.1)

    # Upfront Cost Calculations:
    # Bangalore standard upfront = Monthly Rent + Security Deposit + standard cleaning/brokerage (default 1 month rent)
    rent = pricing_data.rent_amount if pricing_data else 0.0
    deposit = pricing_data.deposit_amount if pricing_data else 0.0
    brokerage_and_paint = rent  # Assume 1-month rent for standard fees in Bangalore
    total_upfront_cost = rent + deposit + brokerage_and_paint

    try:
        data = call_llm_structured(
            llm,
            SYNTHESIS_PROMPT,
            {
                "address_resolved": address_resolved.model_dump() if address_resolved else {},
                "pricing_data": pricing_data.model_dump() if pricing_data else {},
                "vibe_data": vibe_data.model_dump() if vibe_data else {},
                "neighbourhood_data": neighbourhood_data.model_dump() if neighbourhood_data else {},
                "critique_section": ""
            },
            SynthesisResult
        )

        verdict = VerdictCard(
            fair_range_min=data.fair_range_min,
            fair_range_max=data.fair_range_max,
            overpriced_percentage=data.overpriced_percentage,
            total_upfront_cost=total_upfront_cost,
            red_flags=list(data.red_flags),
            neighbourhood_score=data.neighbourhood_score,
            broker_questionnaire=data.broker_questionnaire
        )

        # Proactively check for any additional price drift flag or deposit anomaly flag
        if pricing_data:
            drift_flag_text = "Property pricing is majorly drifted from local comparable averages."
            if pricing_data.price_drift_flag and drift_flag_text not in verdict.red_flags:
                verdict.red_flags.append(drift_flag_text)

            if not pricing_data.deposit_is_normal:
                deposit_flag_text = f"Security deposit demands are high ({pricing_data.deposit_multiplier}x rent)."
                if deposit_flag_text not in verdict.red_flags:
                    verdict.red_flags.append(deposit_flag_text)

        log.info("[Synthesis Agent] Final Verdict Card generated.")
        return {
            "final_verdict": verdict,
            "messages": ["[Synthesis Agent] Compiled all reports into a finalized Verdict Card with custom broker questionnaire."]
        }

    except LLMCallError as e:
        log.error(f"[Synthesis Agent] Error executing synthesis LLM: {e}")
        overpriced = pricing_data.overpriced_percentage if pricing_data else 0.0
        return fallback_synthesis(rent, overpriced, total_upfront_cost, str(e))
