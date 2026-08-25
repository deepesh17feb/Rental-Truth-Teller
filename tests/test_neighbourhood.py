# tests/test_neighbourhood.py
import agents.neighbourhood as neigh_mod
from agents.cache import clear_locality_cache
from agents.state import AgentState, AddressResolved, GeoPoint, NearbyFacility
from agents.facilities import FacilityLookupError


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

    def fake_find_nearby_facilities(geo):
        calls["n"] += 1
        return [
            NearbyFacility(name="Whitefield Metro", facility_type="metro", distance_km=1.1),
            NearbyFacility(name="Test School", facility_type="school", distance_km=0.9),
        ]

    monkeypatch.setattr(neigh_mod, "find_nearby_facilities", fake_find_nearby_facilities)

    result1 = neigh_mod.neighbourhood_node(_state("Whitefield"))
    result2 = neigh_mod.neighbourhood_node(_state("Whitefield"))

    assert result1["neighbourhood_data"].metro_station == "Whitefield Metro"
    assert result1["neighbourhood_data"].metro_distance_km == 1.1
    assert result1["neighbourhood_data"].school_count == 1
    assert result1["neighbourhood_data"].used_fallback is False
    assert calls["n"] == 1  # second call hit the cache
    assert result2["neighbourhood_data"].metro_station == "Whitefield Metro"


def test_neighbourhood_uses_fallback_on_lookup_failure(monkeypatch):
    clear_locality_cache()

    def fake_find_nearby_facilities(geo):
        raise FacilityLookupError("overpass down")

    monkeypatch.setattr(neigh_mod, "find_nearby_facilities", fake_find_nearby_facilities)

    result = neigh_mod.neighbourhood_node(_state("Jayanagar"))

    assert result["neighbourhood_data"].used_fallback is True
    assert result["neighbourhood_data"].school_count == 1
