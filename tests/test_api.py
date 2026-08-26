# tests/test_api.py
from fastapi.testclient import TestClient

import agents.persistence as persistence_mod
from agents.state import AddressResolved, GeoPoint, VerdictCard
from api.main import app

client = TestClient(app)


def _use_temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence_mod.global_config, "VERDICT_DB_PATH", str(tmp_path / "verdicts_test.db"))


def test_list_verdicts_endpoint_returns_saved_verdicts(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    state = {
        "listing_input": "2BHK in Whitefield",
        "address_resolved": AddressResolved(raw_address="x", locality="Whitefield", geo=GeoPoint(lat=12.97, lon=77.75)),
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": VerdictCard(overpriced_percentage=5.0, neighbourhood_score=7.5),
    }
    verdict_id = persistence_mod.save_verdict(state["listing_input"], state)

    response = client.get("/verdicts")

    assert response.status_code == 200
    body = response.json()
    assert any(v["id"] == verdict_id for v in body)


def test_get_verdict_endpoint_returns_404_for_missing_id(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    response = client.get("/verdicts/does-not-exist")

    assert response.status_code == 404


def test_get_verdict_endpoint_returns_full_detail(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    state = {
        "listing_input": "2BHK in Whitefield",
        "address_resolved": AddressResolved(raw_address="x", locality="Whitefield", geo=GeoPoint(lat=12.97, lon=77.75)),
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
    }
    verdict_id = persistence_mod.save_verdict(state["listing_input"], state)

    response = client.get(f"/verdicts/{verdict_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == verdict_id
    assert body["address_resolved"]["locality"] == "Whitefield"
