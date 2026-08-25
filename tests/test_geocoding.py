# tests/test_geocoding.py
import pytest
import responses

from agents.geocoding import geocode_address, GeocodingError
from config.settings import config


@responses.activate
def test_geocode_address_success():
    responses.add(
        responses.GET,
        f"{config.NOMINATIM_BASE_URL}/search",
        json=[{"lat": "12.9698", "lon": "77.7500", "display_name": "Whitefield, Bangalore"}],
        status=200,
    )

    result = geocode_address("Whitefield, Bangalore, Karnataka")

    assert result.lat == 12.9698
    assert result.lon == 77.7500


@responses.activate
def test_geocode_address_sends_identifying_user_agent():
    responses.add(
        responses.GET,
        f"{config.NOMINATIM_BASE_URL}/search",
        json=[{"lat": "12.9698", "lon": "77.7500"}],
        status=200,
    )

    geocode_address("Whitefield, Bangalore")

    sent_headers = responses.calls[0].request.headers
    assert sent_headers["User-Agent"] == config.OSM_USER_AGENT


@responses.activate
def test_geocode_address_no_match_raises_without_retrying():
    responses.add(
        responses.GET,
        f"{config.NOMINATIM_BASE_URL}/search",
        json=[],
        status=200,
    )

    with pytest.raises(GeocodingError):
        geocode_address("Nonexistent Place, Nowhere", wait_min=0.01, wait_max=0.05)

    assert len(responses.calls) == 1  # no-match is not retried


@responses.activate
def test_geocode_address_retries_then_succeeds_on_transient_network_error():
    responses.add(responses.GET, f"{config.NOMINATIM_BASE_URL}/search", status=503)
    responses.add(responses.GET, f"{config.NOMINATIM_BASE_URL}/search", status=503)
    responses.add(
        responses.GET,
        f"{config.NOMINATIM_BASE_URL}/search",
        json=[{"lat": "12.9698", "lon": "77.7500"}],
        status=200,
    )

    result = geocode_address("Whitefield, Bangalore", wait_min=0.01, wait_max=0.05)

    assert result.lat == 12.9698
    assert len(responses.calls) == 3


@responses.activate
def test_geocode_address_malformed_result_raises_geocoding_error_without_retrying():
    # 200 OK but the result is missing "lat" -- this used to escape as a raw
    # KeyError, killing the whole run instead of degrading to the fallback
    # path (which catches GeocodingError).
    responses.add(
        responses.GET,
        f"{config.NOMINATIM_BASE_URL}/search",
        json=[{"lon": "77.7500", "display_name": "Whitefield, Bangalore"}],
        status=200,
    )

    with pytest.raises(GeocodingError):
        geocode_address("Whitefield, Bangalore", wait_min=0.01, wait_max=0.05)

    assert len(responses.calls) == 1  # malformed response is not retried


@responses.activate
def test_geocode_address_non_numeric_lat_raises_geocoding_error():
    responses.add(
        responses.GET,
        f"{config.NOMINATIM_BASE_URL}/search",
        json=[{"lat": "not-a-number", "lon": "77.7500"}],
        status=200,
    )

    with pytest.raises(GeocodingError):
        geocode_address("Whitefield, Bangalore", wait_min=0.01, wait_max=0.05)

    assert len(responses.calls) == 1


@responses.activate
def test_geocode_address_raises_after_max_attempts_on_persistent_network_error():
    responses.add(responses.GET, f"{config.NOMINATIM_BASE_URL}/search", status=503)
    responses.add(responses.GET, f"{config.NOMINATIM_BASE_URL}/search", status=503)

    with pytest.raises(GeocodingError):
        geocode_address("Whitefield, Bangalore", max_attempts=2, wait_min=0.01, wait_max=0.05)

    assert len(responses.calls) == 2
