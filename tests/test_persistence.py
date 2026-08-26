# tests/test_persistence.py
import agents.persistence as persistence_mod
from agents.persistence import save_verdict, list_verdicts, get_verdict
from agents.state import AddressResolved, GeoPoint, PricingAnalysis, VibeAnalysis, NeighbourhoodAnalysis, VerdictCard


def _sample_final_state(listing_input: str = "2BHK in Whitefield, rent 50000") -> dict:
    return {
        "listing_input": listing_input,
        "address_resolved": AddressResolved(raw_address="x", locality="Whitefield", geo=GeoPoint(lat=12.97, lon=77.75)),
        "pricing_data": PricingAnalysis(rent_amount=50000.0),
        "vibe_data": VibeAnalysis(listing_nlp_sentiment="Warm"),
        "neighbourhood_data": NeighbourhoodAnalysis(metro_station="Whitefield Metro"),
        "final_verdict": VerdictCard(overpriced_percentage=5.0, neighbourhood_score=7.5),
        "messages": [],
    }


def _use_temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence_mod.global_config, "VERDICT_DB_PATH", str(tmp_path / "verdicts_test.db"))


def test_save_then_get_round_trip_preserves_all_fields(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    state = _sample_final_state()

    verdict_id = save_verdict(state["listing_input"], state)
    detail = get_verdict(verdict_id)

    assert detail is not None
    assert detail.id == verdict_id
    assert detail.listing_input == state["listing_input"]
    assert detail.address_resolved["locality"] == "Whitefield"
    assert detail.pricing_data["rent_amount"] == 50000.0
    assert detail.vibe_data["listing_nlp_sentiment"] == "Warm"
    assert detail.neighbourhood_data["metro_station"] == "Whitefield Metro"
    assert detail.final_verdict["overpriced_percentage"] == 5.0


def test_save_then_list_returns_newest_first(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    id1 = save_verdict("first listing", _sample_final_state("first listing"))
    id2 = save_verdict("second listing", _sample_final_state("second listing"))

    summaries = list_verdicts(limit=20)

    assert [s.id for s in summaries[:2]] == [id2, id1]


def test_list_respects_limit(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    for i in range(5):
        save_verdict(f"listing {i}", _sample_final_state(f"listing {i}"))

    summaries = list_verdicts(limit=3)

    assert len(summaries) == 3


def test_get_verdict_returns_none_for_nonexistent_id(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    assert get_verdict("does-not-exist") is None


def test_none_sub_field_round_trips_as_none(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    state = _sample_final_state()
    state["final_verdict"] = None

    verdict_id = save_verdict(state["listing_input"], state)
    detail = get_verdict(verdict_id)

    assert detail.final_verdict is None
