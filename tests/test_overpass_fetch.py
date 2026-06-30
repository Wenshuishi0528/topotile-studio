import requests

from city_modeler import osm


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


def test_overpass_query_includes_building_parts_and_green_relations():
    query = osm.overpass_query(47.62, -122.355, 47.626, -122.3455)

    assert 'way["building:part"]' in query
    assert 'relation["building"]' in query
    assert 'relation["building:part"]' in query
    assert 'way["amenity"="parking"]' in query
    assert 'relation["amenity"="parking"]' in query
    assert 'relation["leisure"~' in query
    assert 'way["landcover"~' in query
    assert 'relation["landcover"~' in query
    assert 'way["barrier"~"hedge|planter"]' in query
    assert 'relation["barrier"~"hedge|planter"]' in query
    assert 'way["man_made"="planter"]' in query
    assert 'shrubbery' in query
    assert 'plant_nursery' in query


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
