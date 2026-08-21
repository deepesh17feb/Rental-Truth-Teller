from agents.fallbacks import (
    fallback_address_resolution,
    fallback_vibe_analysis,
    fallback_neighbourhood_analysis,
    fallback_synthesis,
)


def test_fallback_address_resolution_flags_used_fallback():
    result = fallback_address_resolution("some listing", "boom")
    assert result["address_resolved"].used_fallback is True


def test_fallback_vibe_analysis_flags_used_fallback():
    result = fallback_vibe_analysis("boom")
    assert result["vibe_data"].used_fallback is True


def test_fallback_neighbourhood_analysis_returns_facilities():
    base_metro_dist, facilities = fallback_neighbourhood_analysis("Whitefield", "Whitefield Metro Station")
    assert base_metro_dist == 1.5
    assert len(facilities) == 4


def test_fallback_synthesis_flags_used_fallback():
    result = fallback_synthesis(rent=50000.0, overpriced_percentage=5.0, total_upfront_cost=150000.0, error_msg="boom")
    assert result["final_verdict"].used_fallback is True
