import requests
import pytest

from city_modeler.cancel import GenerationCancelled
from city_modeler import osm


@pytest.fixture(autouse=True)
def isolate_osm_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(osm, "OSM_CACHE_DIR", tmp_path / "osm")


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_fetch_osm_json_sends_user_agent(monkeypatch):
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse(200, {"elements": []})

    monkeypatch.setattr(requests, "post", fake_post)

    result = osm.fetch_osm_json(47.62, -122.355, 47.626, -122.3455)

    assert result == {"elements": []}
    assert calls[0]["headers"]["User-Agent"] == osm.OVERPASS_USER_AGENT
    assert calls[0]["headers"]["Accept"] == "application/json"


def test_fetch_osm_json_reuses_cached_query(monkeypatch):
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append({"url": url, "data": data})
        return FakeResponse(200, {"elements": [{"type": "way", "id": 1}]})

    monkeypatch.setattr(requests, "post", fake_post)

    first = osm.fetch_osm_json(47.62, -122.355, 47.626, -122.3455)
    second = osm.fetch_osm_json(47.62, -122.355, 47.626, -122.3455)

    assert first == second
    assert len(calls) == 1


def test_overpass_query_includes_building_parts_and_green_relations():
    query = osm.overpass_query(47.62, -122.355, 47.626, -122.3455)

    assert 'way["building:part"]' in query
    assert 'relation["building"]' in query
    assert 'relation["building:part"]' in query
    assert 'way["railway"~"rail|narrow_gauge|light_rail|tram|monorail|subway"]' in query
    assert 'node["railway"~"station|halt|subway_entrance|tram_stop"]' in query
    assert 'way["public_transport"="station"]' in query
    assert 'node["station"~"subway|train|rail|light_rail"]' in query
    assert 'way["power"~"line|minor_line"]' in query
    assert 'node["power"~"tower|pole"]' in query
    assert 'way["power"~"plant"]' in query
    assert 'relation["power"~"plant"]' in query
    assert 'way["amenity"="parking"]' in query
    assert 'relation["amenity"="parking"]' in query
    assert 'way["aeroway"~"runway|taxiway|apron"]' in query
    assert 'relation["aeroway"~"runway|taxiway|apron"]' in query
    assert 'relation["leisure"~' in query
    assert 'way["landcover"~' in query
    assert 'relation["landcover"~' in query
    assert 'way["barrier"~"hedge|planter"]' in query
    assert 'relation["barrier"~"hedge|planter"]' in query
    assert 'way["man_made"="planter"]' in query
    assert 'shrubbery' in query
    assert 'plant_nursery' in query
    assert 'way["landuse"~"residential|industrial|commercial|retail' in query
    assert 'relation["landuse"~"residential|industrial|commercial|retail' in query
    assert 'way["amenity"~"hospital|clinic|school|university' in query
    assert 'relation["healthcare"]' in query
    assert 'way["tourism"~"theme_park|attraction|museum|hotel"]' in query
    assert 'relation["historic"~"district|yes|archaeological_site|monument|castle"]' in query
    assert 'way["place"="city_block"]' in query
    assert 'way["office"]' in query


def test_water_overpass_query_fetches_members_and_water_relations():
    query = osm.water_overpass_query(47.62, -122.355, 47.626, -122.3455)

    assert 'way["natural"="water"]' in query
    assert 'relation["natural"="water"]' in query
    assert 'relation["waterway"="riverbank"]' in query
    assert '(._;>;);' in query
    assert 'out body geom;' in query


def test_merge_osm_json_keeps_richer_supplemental_geometry():
    primary = {
        "elements": [
            {"type": "way", "id": 1, "tags": {"natural": "water"}, "geometry": [{"lat": 0.0, "lon": 0.0}]},
            {"type": "way", "id": 2, "tags": {"building": "yes"}},
        ]
    }
    supplemental = {
        "elements": [
            {
                "type": "way",
                "id": 1,
                "tags": {"natural": "water"},
                "geometry": [
                    {"lat": 0.0, "lon": 0.0},
                    {"lat": 0.0, "lon": 0.1},
                    {"lat": 0.1, "lon": 0.1},
                ],
            }
        ]
    }

    merged = osm.merge_osm_json(primary, supplemental)
    by_id = {(element["type"], element["id"]): element for element in merged["elements"]}

    assert len(merged["elements"]) == 2
    assert len(by_id[("way", 1)]["geometry"]) == 3
    assert by_id[("way", 2)]["tags"]["building"] == "yes"


def test_fetch_osm_json_falls_back_from_default_endpoint(monkeypatch):
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse(406, text="Not Acceptable")
        return FakeResponse(200, {"elements": [{"type": "way"}]})

    monkeypatch.setattr(requests, "post", fake_post)

    result = osm.fetch_osm_json(47.62, -122.355, 47.626, -122.3455)

    assert result == {"elements": [{"type": "way"}]}
    assert calls == osm.FALLBACK_OVERPASS_URLS


def test_fetch_osm_json_tiled_deduplicates_elements(monkeypatch):
    calls = []

    def fake_fetch(south, west, north, east, overpass_url, **kwargs):
        calls.append((south, west, north, east))
        return {
            "elements": [
                {"type": "way", "id": 1, "tags": {"highway": "residential"}},
                {"type": "way", "id": len(calls) + 1, "tags": {"building": "yes"}},
            ]
        }

    monkeypatch.setattr(osm, "fetch_osm_json", fake_fetch)
    monkeypatch.setattr(osm.time, "sleep", lambda _seconds: None)

    result = osm.fetch_osm_json_tiled(
        47.0,
        -122.0,
        47.04,
        -121.96,
        tile_size_km=2.0,
    )

    ids = [(element["type"], element["id"]) for element in result["elements"]]
    assert len(calls) > 1
    assert ids.count(("way", 1)) == 1
    assert result["tile_count"] == len(calls)


def test_fetch_osm_json_tiled_keeps_richer_duplicate_geometry(monkeypatch):
    calls = []

    def fake_fetch(south, west, north, east, overpass_url, **kwargs):
        calls.append((south, west, north, east))
        geometry = [{"lat": 0.0, "lon": 0.0}] if len(calls) == 1 else [
            {"lat": 0.0, "lon": 0.0},
            {"lat": 0.0, "lon": 0.1},
            {"lat": 0.1, "lon": 0.1},
        ]
        return {
            "elements": [
                {"type": "way", "id": 1, "tags": {"highway": "residential"}, "geometry": geometry},
            ]
        }

    monkeypatch.setattr(osm, "fetch_osm_json", fake_fetch)
    monkeypatch.setattr(osm.time, "sleep", lambda _seconds: None)

    result = osm.fetch_osm_json_tiled(47.0, -122.0, 47.04, -121.96, tile_size_km=2.0)

    assert len(calls) > 1
    assert len(result["elements"]) == 1
    assert len(result["elements"][0]["geometry"]) == 3


def test_fetch_osm_json_tiled_subdivides_failed_tile(monkeypatch):
    calls = []

    def fake_fetch(south, west, north, east, overpass_url, **kwargs):
        calls.append((south, west, north, east))
        if north - south > 0.006:
            raise osm.OverpassFetchError("tile too large")
        return {
            "elements": [
                {"type": "way", "id": len(calls), "tags": {"building": "yes"}},
            ]
        }

    monkeypatch.setattr(osm, "fetch_osm_json", fake_fetch)
    monkeypatch.setattr(osm.time, "sleep", lambda _seconds: None)

    result = osm.fetch_osm_json_tiled(47.0, -122.0, 47.01, -121.99, tile_size_km=20.0)

    assert len(calls) == 6
    assert len(result["elements"]) == 4
    assert result["tile_errors"] == []


def test_fetch_osm_json_tiled_raises_instead_of_partial_output(monkeypatch):
    def fake_fetch(south, west, north, east, overpass_url, **kwargs):
        raise osm.OverpassFetchError("rate limited")

    monkeypatch.setattr(osm, "fetch_osm_json", fake_fetch)
    monkeypatch.setattr(osm.time, "sleep", lambda _seconds: None)

    try:
        osm.fetch_osm_json_tiled(47.0, -122.0, 47.04, -121.96, tile_size_km=2.0)
    except osm.OverpassFetchError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected OverpassFetchError")

    assert "generation stopped to avoid missing" in message


def test_fetch_osm_json_raises_clear_message(monkeypatch):
    def fake_post(url, data, headers, timeout):
        return FakeResponse(429, text="rate limited")

    monkeypatch.setattr(requests, "post", fake_post)

    try:
        osm.fetch_osm_json(47.62, -122.355, 47.626, -122.3455)
    except osm.OverpassFetchError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected OverpassFetchError")

    assert "No API key is required" in message
    assert "try a smaller map selection" in message
    assert "HTTP 429" in message


def test_fetch_osm_json_honors_cancel_check_before_network(monkeypatch):
    def fake_post(*args, **kwargs):
        raise AssertionError("Overpass should not be called after cancellation")

    def cancel_now():
        raise GenerationCancelled("Cancelled")

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(GenerationCancelled):
        osm.fetch_osm_json(47.62, -122.355, 47.626, -122.3455, cancel_check=cancel_now)
