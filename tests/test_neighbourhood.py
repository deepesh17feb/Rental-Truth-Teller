from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.neighbourhood as neigh_mod
from agents.cache import clear_locality_cache
from agents.state import AgentState, AddressResolved, GeoPoint


def _state(locality: str) -> AgentState:
    return {
        "listing_input": "listing",
        "address_resolved": AddressResolved(
            raw_address="x", locality=locality, structured_address=f"{locality}, Bangalore",
            geo=GeoPoint(lat=12.97, lon=77.75)
        ),
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def test_neighbourhood_resolves_and_caches_by_locality(monkeypatch):
    clear_locality_cache()
    calls = {"n": 0}

    def dispatch(_prompt_value):
        calls["n"] += 1
        return AIMessage(
            content='{"metro_station": "Whitefield Metro", "metro_distance_km": 1.1, "facilities": [{"name": "Test School", "facility_type": "school", "distance_km": 0.9}]}'
        )

    monkeypatch.setattr(neigh_mod, "get_llm", lambda temperature=0.1: RunnableLambda(dispatch))

    result1 = neigh_mod.neighbourhood_node(_state("Whitefield"))
    result2 = neigh_mod.neighbourhood_node(_state("Whitefield"))

    assert result1["neighbourhood_data"].metro_station == "Whitefield Metro"
    assert result1["neighbourhood_data"].school_count == 1
    assert result1["neighbourhood_data"].used_fallback is False
    assert calls["n"] == 1  # second call hit the cache
    assert result2["neighbourhood_data"].metro_station == "Whitefield Metro"


def test_neighbourhood_uses_fallback_on_llm_failure(monkeypatch):
    clear_locality_cache()
    monkeypatch.setattr(
        neigh_mod, "get_llm", lambda temperature=0.1: RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    )

    result = neigh_mod.neighbourhood_node(_state("Jayanagar"))

    assert result["neighbourhood_data"].used_fallback is True
    assert result["neighbourhood_data"].school_count == 1
