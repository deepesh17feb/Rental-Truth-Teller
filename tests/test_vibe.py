from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.vibe as vibe_mod
from agents.state import AgentState


def _state(listing_input: str) -> AgentState:
    return {
        "listing_input": listing_input,
        "address_resolved": None,
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def test_vibe_check_success(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"amenity_vs_claim_diffs": ["claims metro nearby but 20 min walk"], "community_signals": ["family friendly"], "diet_pet_lifestyle": ["pure veg only"], "listing_nlp_sentiment": "Pressuring"}'
        )
    )
    monkeypatch.setattr(vibe_mod, "get_llm", lambda temperature=0.1: fake_llm)

    result = vibe_mod.vibe_check_node(_state("2BHK, pure veg only, near metro (20 min walk)"))

    assert result["vibe_data"].listing_nlp_sentiment == "Pressuring"
    assert result["vibe_data"].used_fallback is False
    assert "pure veg only" in result["vibe_data"].diet_pet_lifestyle


def test_vibe_check_uses_fallback_on_llm_failure(monkeypatch):
    fake_llm = RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(vibe_mod, "get_llm", lambda temperature=0.1: fake_llm)

    result = vibe_mod.vibe_check_node(_state("2BHK listing"))

    assert result["vibe_data"].used_fallback is True
    assert result["vibe_data"].listing_nlp_sentiment == "Error"
