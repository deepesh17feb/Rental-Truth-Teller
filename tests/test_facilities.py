# tests/test_facilities.py
import pytest
import responses

from agents.facilities import find_nearby_facilities, haversine_km, FacilityLookupError
from agents.state import GeoPoint
from config.settings import config

WHITEFIELD = GeoPoint(lat=12.9698, lon=77.7500)


def test_haversine_km_known_distance():
    # 1 degree of longitude at the equator is ~111.19 km (2*pi*R/360, R=6371km)
    a = GeoPoint(lat=0.0, lon=0.0)
    b = GeoPoint(lat=0.0, lon=1.0)
    assert abs(haversine_km(a, b) - 111.19) < 0.1


def test_haversine_km_zero_for_same_point():
    assert haversine_km(WHITEFIELD, WHITEFIELD) == 0.0


@responses.activate
def test_find_nearby_facilities_returns_closest_per_type_sorted_by_distance():
    elements = [
        {"type": "node", "id": 1, "lat": 12.975, "lon": 77.755, "tags": {"amenity": "school", "name": "Far School"}},
        {"type": "node", "id": 2, "lat": 12.970, "lon": 77.751, "tags": {"amenity": "school", "name": "Near School"}},
        {"type": "node", "id": 3, "lat": 12.971, "lon": 77.749, "tags": {"amenity": "hospital", "name": "City Hospital"}},
        {"type": "node", "id": 4, "lat": 12.969, "lon": 77.751, "tags": {"shop": "supermarket", "name": "Big Bazaar"}},
        {"type": "node", "id": 5, "lat": 12.972, "lon": 77.753, "tags": {"railway": "station", "name": "Whitefield Metro"}},
        {"type": "node", "id": 6, "lat": 12.980, "lon": 77.760, "tags": {"amenity": "restaurant", "name": "Not A Facility"}},
    ]
    responses.add(
        responses.POST,
        config.OVERPASS_BASE_URL,
        json={"elements": elements},
        status=200,
    )

    result = find_nearby_facilities(WHITEFIELD)

    school_names = [f.name for f in result if f.facility_type == "school"]
    assert school_names == ["Near School", "Far School"]  # closest first
    assert any(f.name == "City Hospital" and f.facility_type == "hospital" for f in result)
    assert any(f.name == "Big Bazaar" and f.facility_type == "market" for f in result)
    assert any(f.name == "Whitefield Metro" and f.facility_type == "metro" for f in result)
    assert not any(f.name == "Not A Facility" for f in result)  # unmapped tag excluded


@responses.activate
def test_find_nearby_facilities_dedupes_by_element_id():
    # Same element id repeated 3x, facility_type="school" (limit 2, not 1) so
    # the type limit alone can't explain a result of 1 -- only dedup can.
    # Without dedup this would yield up to 2 "Near School" entries (sliced by
    # the type limit); with dedup there is only ever 1 candidate to begin with.
    elements = [
        {"type": "node", "id": 9, "lat": 12.970, "lon": 77.751, "tags": {"amenity": "school", "name": "Near School"}},
        {"type": "node", "id": 9, "lat": 12.970, "lon": 77.751, "tags": {"amenity": "school", "name": "Near School"}},
        {"type": "node", "id": 9, "lat": 12.970, "lon": 77.751, "tags": {"amenity": "school", "name": "Near School"}},
    ]
    responses.add(
        responses.POST,
        config.OVERPASS_BASE_URL,
        json={"elements": elements},
        status=200,
    )

    result = find_nearby_facilities(WHITEFIELD)

    school_matches = [f for f in result if f.facility_type == "school"]
    assert len(school_matches) == 1


@responses.activate
def test_find_nearby_facilities_skips_unnamed_elements():
    elements = [
        {"type": "node", "id": 8, "lat": 12.970, "lon": 77.751, "tags": {"amenity": "school"}},  # no name
    ]
    responses.add(
        responses.POST,
        config.OVERPASS_BASE_URL,
        json={"elements": elements},
        status=200,
    )

    result = find_nearby_facilities(WHITEFIELD)

    assert result == []


@responses.activate
def test_find_nearby_facilities_empty_result_is_not_an_error():
    responses.add(
        responses.POST,
        config.OVERPASS_BASE_URL,
        json={"elements": []},
        status=200,
    )

    result = find_nearby_facilities(WHITEFIELD)

    assert result == []


@responses.activate
def test_find_nearby_facilities_raises_after_max_attempts_on_persistent_network_error():
    responses.add(responses.POST, config.OVERPASS_BASE_URL, status=503)
    responses.add(responses.POST, config.OVERPASS_BASE_URL, status=503)

    with pytest.raises(FacilityLookupError):
        find_nearby_facilities(WHITEFIELD, max_attempts=2, wait_min=0.01, wait_max=0.05)

    assert len(responses.calls) == 2
