import pytest
from unittest.mock import Mock, MagicMock

import agents.service as service_mod


def test_verify_listing_persists_result_on_success(monkeypatch):
    fake_final_state = {"listing_input": "2BHK in Whitefield", "final_verdict": None}

    calls = {}

    def fake_save_verdict(listing_input, final_state):
        calls["listing_input"] = listing_input
        calls["final_state"] = final_state
        return "some-id"

    mock_app = MagicMock()
    mock_app.invoke.return_value = fake_final_state

    monkeypatch.setattr(service_mod, "app", mock_app)
    monkeypatch.setattr(service_mod, "save_verdict", fake_save_verdict)

    result = service_mod.TruthTellerService.verify_listing("2BHK in Whitefield")

    assert result == fake_final_state
    assert calls["listing_input"] == "2BHK in Whitefield"
    assert calls["final_state"] == fake_final_state


def test_verify_listing_returns_result_even_if_persistence_fails(monkeypatch):
    fake_final_state = {"listing_input": "2BHK in Whitefield", "final_verdict": None}

    def failing_save_verdict(listing_input, final_state):
        raise RuntimeError("disk full")

    mock_app = MagicMock()
    mock_app.invoke.return_value = fake_final_state

    monkeypatch.setattr(service_mod, "app", mock_app)
    monkeypatch.setattr(service_mod, "save_verdict", failing_save_verdict)

    result = service_mod.TruthTellerService.verify_listing("2BHK in Whitefield")

    assert result == fake_final_state


def test_verify_listing_does_not_persist_on_graph_failure(monkeypatch):
    calls = {"n": 0}

    def fake_save_verdict(listing_input, final_state):
        calls["n"] += 1
        return "id"

    def failing_invoke(state):
        raise RuntimeError("graph exploded")

    mock_app = MagicMock()
    mock_app.invoke.side_effect = failing_invoke

    monkeypatch.setattr(service_mod, "app", mock_app)
    monkeypatch.setattr(service_mod, "save_verdict", fake_save_verdict)

    with pytest.raises(RuntimeError):
        service_mod.TruthTellerService.verify_listing("2BHK in Whitefield")

    assert calls["n"] == 0
