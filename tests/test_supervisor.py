# tests/test_supervisor.py
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agents.supervisor as supervisor_mod
from agents.state import AgentState, GeoPoint
from agents.geocoding import GeocodingError


def _base_state(listing_input: str) -> AgentState:
    return {
        "listing_input": listing_input,
        "address_resolved": None,
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": [],
    }


def test_supervisor_uses_static_dictionary_when_locality_recognized():
    state = _base_state("2BHK for rent in Whitefield, Bangalore")
    result = supervisor_mod.supervisor_node(state)

    assert result["address_resolved"].locality == "Whitefield"
    assert result["address_resolved"].used_fallback is False
    assert result["address_resolved"].confidence == 0.9


def test_supervisor_falls_through_to_real_geocoding_for_unknown_locality(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"locality": "JP Nagar", "structured_address": "JP Nagar, Bangalore, Karnataka"}'
        )
    )
    monkeypatch.setattr(supervisor_mod, "get_llm", lambda temperature=0.1: fake_llm)
    monkeypatch.setattr(
        supervisor_mod, "geocode_address", lambda query: GeoPoint(lat=12.9077, lon=77.5928)
    )

    state = _base_state("2BHK for rent in JP Nagar")
    result = supervisor_mod.supervisor_node(state)

    assert result["address_resolved"].locality == "JP Nagar"
    assert result["address_resolved"].geo.lat == 12.9077
    assert result["address_resolved"].used_fallback is False


def test_supervisor_uses_fallback_when_llm_call_fails(monkeypatch):
    fake_llm = RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(supervisor_mod, "get_llm", lambda temperature=0.1: fake_llm)

    state = _base_state("2BHK for rent in JP Nagar")
    result = supervisor_mod.supervisor_node(state)

    assert result["address_resolved"].used_fallback is True
    assert result["address_resolved"].locality == "Whitefield"


def test_supervisor_uses_fallback_when_geocoding_fails(monkeypatch):
    fake_llm = RunnableLambda(
        lambda _: AIMessage(
            content='{"locality": "JP Nagar", "structured_address": "JP Nagar, Bangalore, Karnataka"}'
        )
    )
    monkeypatch.setattr(supervisor_mod, "get_llm", lambda temperature=0.1: fake_llm)

    def _raise_geocoding_error(query):
        raise GeocodingError(f"No match for {query!r}")

    monkeypatch.setattr(supervisor_mod, "geocode_address", _raise_geocoding_error)

    state = _base_state("2BHK for rent in JP Nagar")
    result = supervisor_mod.supervisor_node(state)

    assert result["address_resolved"].used_fallback is True
    assert result["address_resolved"].locality == "Whitefield"
