# tests/test_synthesis.py
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.synthesis as synthesis_mod
from agents.state import AgentState, PricingAnalysis


def _state(pricing_data=None) -> AgentState:
    return {
        "listing_input": "listing",
        "address_resolved": None,
        "pricing_data": pricing_data,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def test_synthesis_success(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"fair_range_min": 45000.0, "fair_range_max": 55000.0, "overpriced_percentage": 5.0, "red_flags": ["broker fee undisclosed"], "neighbourhood_score": 7.5, "broker_questionnaire": ["Why is deposit so high?"]}'
        )
    )
    monkeypatch.setattr(synthesis_mod, "get_llm", lambda temperature=0.1: fake_llm)

    pricing = PricingAnalysis(rent_amount=50000.0, deposit_amount=300000.0)
    result = synthesis_mod.synthesis_node(_state(pricing_data=pricing))

    verdict = result["final_verdict"]
    assert verdict.fair_range_min == 45000.0
    assert verdict.used_fallback is False
    assert verdict.total_upfront_cost == 50000.0 + 300000.0 + 50000.0


def test_synthesis_appends_price_drift_flag_exactly_once(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"fair_range_min": 45000.0, "fair_range_max": 55000.0, "overpriced_percentage": 40.0, "red_flags": [], "neighbourhood_score": 7.5, "broker_questionnaire": []}'
        )
    )
    monkeypatch.setattr(synthesis_mod, "get_llm", lambda temperature=0.1: fake_llm)

    pricing = PricingAnalysis(rent_amount=50000.0, deposit_amount=600000.0, price_drift_flag=True, deposit_is_normal=False, deposit_multiplier=12.0)
    result = synthesis_mod.synthesis_node(_state(pricing_data=pricing))

    red_flags = result["final_verdict"].red_flags
    assert red_flags.count("Property pricing is majorly drifted from local comparable averages.") == 1
    assert any("Security deposit demands are high" in f for f in red_flags)


def test_synthesis_uses_fallback_on_llm_failure(monkeypatch):
    fake_llm = RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(synthesis_mod, "get_llm", lambda temperature=0.1: fake_llm)

    pricing = PricingAnalysis(rent_amount=50000.0, deposit_amount=300000.0)
    result = synthesis_mod.synthesis_node(_state(pricing_data=pricing))

    assert result["final_verdict"].used_fallback is True
