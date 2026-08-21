# tests/test_pricing.py
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.pricing as pricing_mod
from agents.cache import clear_locality_cache
from agents.state import AgentState, AddressResolved, GeoPoint


def _state_with_locality(locality: str, listing_input: str) -> AgentState:
    return {
        "listing_input": listing_input,
        "address_resolved": AddressResolved(
            raw_address=listing_input,
            locality=locality,
            geo=GeoPoint(lat=12.97, lon=77.75),
        ),
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def test_pricing_uses_llm_benchmarks_and_caches_by_locality(monkeypatch):
    clear_locality_cache()
    monkeypatch.setattr(
        pricing_mod, "get_elasticsearch_client", lambda: (_ for _ in ()).throw(RuntimeError("no ES"))
    )
    monkeypatch.setattr("glob.glob", lambda pattern: [])

    benchmark_calls = {"n": 0}

    def dispatch(prompt_value):
        text = prompt_value.to_string()
        if "financial extractor" in text.lower():
            return AIMessage(content='{"rent": 50000, "deposit": 300000, "area_sqft": 1000}')
        benchmark_calls["n"] += 1
        return AIMessage(content='{"avg_price_per_sqft": 45.0, "std_price_per_sqft": 5.0}')

    monkeypatch.setattr(pricing_mod, "get_llm", lambda temperature=0.1: RunnableLambda(dispatch))

    state = _state_with_locality("Whitefield", "2BHK in Whitefield, rent 50000")

    result1 = pricing_mod.pricing_node(state)
    result2 = pricing_mod.pricing_node(state)

    assert result1["pricing_data"].market_avg_price_per_sqft == 45.0
    assert result2["pricing_data"].market_avg_price_per_sqft == 45.0
    assert result1["pricing_data"].used_fallback is False
    assert benchmark_calls["n"] == 1  # second pricing_node call hit the cache


def test_pricing_sets_used_fallback_when_llm_benchmarks_fail(monkeypatch):
    clear_locality_cache()
    monkeypatch.setattr(
        pricing_mod, "get_elasticsearch_client", lambda: (_ for _ in ()).throw(RuntimeError("no ES"))
    )
    monkeypatch.setattr("glob.glob", lambda pattern: [])

    def dispatch(prompt_value):
        text = prompt_value.to_string()
        if "financial extractor" in text.lower():
            return AIMessage(content='{"rent": 50000, "deposit": 300000, "area_sqft": 1000}')
        raise RuntimeError("LLM down")

    monkeypatch.setattr(pricing_mod, "get_llm", lambda temperature=0.1: RunnableLambda(dispatch))

    state = _state_with_locality("Jayanagar", "2BHK in Jayanagar, rent 50000")
    result = pricing_mod.pricing_node(state)

    assert result["pricing_data"].used_fallback is True
    assert result["pricing_data"].market_avg_price_per_sqft == 40.0
