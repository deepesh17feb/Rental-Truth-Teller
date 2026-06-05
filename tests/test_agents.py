"""
tests/test_agents.py
────────────────────
Integration tests for the Multi-Agent Graph using Mock LLM.
"""

import pytest
import os
from agents.service import TruthTellerService
from config.settings import config

@pytest.fixture(autouse=True)
def setup_mock_env():
    """Ensure we use the mock LLM for testing."""
    original_provider = os.environ.get("LLM_PROVIDER")
    original_mock = os.environ.get("USE_MOCK_LLM")

    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["USE_MOCK_LLM"] = "true"

    yield

    if original_provider:
        os.environ["LLM_PROVIDER"] = original_provider
    else:
        del os.environ["LLM_PROVIDER"]

    if original_mock:
        os.environ["USE_MOCK_LLM"] = original_mock
    else:
        del os.environ["USE_MOCK_LLM"]

def test_truth_teller_flow_whitefield():
    """Tests the full agent graph flow with a Whitefield listing."""
    listing = "2BHK in Whitefield, rent 45000, deposit 2L, 1200 sqft, near metro"
    result = TruthTellerService.verify_listing(listing)

    assert "address_resolved" in result
    assert result["address_resolved"].locality == "Whitefield"

    assert "pricing_data" in result
    assert result["pricing_data"].rent_amount == 45000.0

    assert "final_verdict" in result
    verdict = result["final_verdict"]
    assert verdict.fair_range_min > 0
    assert len(verdict.broker_questionnaire) > 0

def test_truth_teller_flow_koramangala():
    """Tests the full agent graph flow with a Koramangala listing."""
    listing = "Flat in Koramangala, rent 85000, 1100 sqft, pure veg"
    result = TruthTellerService.verify_listing(listing)

    assert result["address_resolved"].locality == "Koramangala"
    assert result["pricing_data"].rent_amount == 85000.0

    verdict = result["final_verdict"]
    # Check if red flags contain veg restriction (mock logic)
    has_veg_flag = any("vegetarian" in flag.lower() for flag in verdict.red_flags)
    assert has_veg_flag
