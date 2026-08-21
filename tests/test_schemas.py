import pytest
from pydantic import ValidationError

from agents.schemas import (
    GeocodeResult,
    FinancialsResult,
    BenchmarksResult,
    VibeResult,
    FacilityResult,
    NeighbourhoodResult,
    SynthesisResult,
)


def test_geocode_result_requires_lat_lon():
    result = GeocodeResult(
        locality="Whitefield",
        structured_address="Whitefield, Bangalore, Karnataka",
        lat=12.9698,
        lon=77.7500,
    )
    assert result.lat == 12.9698

    with pytest.raises(ValidationError):
        GeocodeResult(locality="Whitefield", structured_address="x")


def test_financials_result_defaults():
    result = FinancialsResult()
    assert result.rent == 0.0
    assert result.deposit == 0.0
    assert result.area_sqft is None


def test_benchmarks_result_requires_both_fields():
    result = BenchmarksResult(avg_price_per_sqft=45.0, std_price_per_sqft=6.0)
    assert result.avg_price_per_sqft == 45.0

    with pytest.raises(ValidationError):
        BenchmarksResult(avg_price_per_sqft=45.0)


def test_vibe_result_defaults():
    result = VibeResult()
    assert result.amenity_vs_claim_diffs == []
    assert result.listing_nlp_sentiment == "Neutral"


def test_neighbourhood_result_with_facilities():
    result = NeighbourhoodResult(
        metro_station="Whitefield Metro",
        metro_distance_km=1.2,
        facilities=[
            FacilityResult(name="Test School", facility_type="school", distance_km=0.8)
        ],
    )
    assert len(result.facilities) == 1
    assert result.facilities[0].facility_type == "school"


def test_synthesis_result_requires_core_fields():
    result = SynthesisResult(
        fair_range_min=32000.0,
        fair_range_max=38000.0,
        overpriced_percentage=12.5,
        neighbourhood_score=8.0,
    )
    assert result.red_flags == []
    assert result.broker_questionnaire == []

    with pytest.raises(ValidationError):
        SynthesisResult(fair_range_min=32000.0)
