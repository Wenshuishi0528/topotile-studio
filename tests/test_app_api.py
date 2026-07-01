import pytest
import asyncio
import json
from io import BytesIO
from fastapi import HTTPException
from fastapi import UploadFile

from app import main


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class FakeFuture:
    def __init__(self, can_cancel: bool):
        self.can_cancel = can_cancel

    def cancel(self) -> bool:
        return self.can_cancel


def test_geocode_uses_nominatim_with_user_agent(monkeypatch):
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return FakeResponse(200, [{
            "lat": "47.655548",
            "lon": "-122.303200",
            "display_name": "University of Washington, Seattle",
            "boundingbox": ["47.64", "47.67", "-122.32", "-122.29"],
    }])

    monkeypatch.setattr(main.requests, "get", fake_get)

    result = main.geocode(q="University of Washington")

    assert result["lat"] == 47.655548
    assert result["lon"] == -122.3032
    assert result["bbox"] == [47.64, -122.32, 47.67, -122.29]
    assert calls[0]["url"] == main.NOMINATIM_SEARCH_URL
    assert calls[0]["headers"]["User-Agent"] == main.GEOCODE_USER_AGENT
    assert calls[0]["params"]["limit"] == 1


def test_geocode_returns_404_when_address_not_found(monkeypatch):
    monkeypatch.setattr(main.requests, "get", lambda *args, **kwargs: FakeResponse(200, []))

    with pytest.raises(HTTPException) as exc:
        main.geocode(q="not a real place")

    assert exc.value.status_code == 404
    assert exc.value.detail == "Address not found."


def test_clear_cache_keeps_terrain_cache_when_not_selected(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    outputs = tmp_path / "outputs"
    cache = tmp_path / "cache"
    terrain = cache / "terrain_tiles"
    osm = cache / "osm"
    elevation = cache / "elevation"
    for path in (jobs, outputs, terrain, osm, elevation):
        path.mkdir(parents=True)
    (jobs / "status.json").write_text("{}", encoding="utf-8")
    (outputs / "city_model.3mf").write_text("model", encoding="utf-8")
    (terrain / "tile.tif").write_text("terrain", encoding="utf-8")
    (osm / "query.json").write_text("{}", encoding="utf-8")
    (elevation / "points.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "JOBS_DIR", jobs)
    monkeypatch.setattr(main, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(main, "CACHE_DIR", cache)

    result = main.clear_cache({"generated": True, "terrain": False})

    assert result["removed_bytes"] > 0
    assert not any(jobs.iterdir())
    assert not any(outputs.iterdir())
    assert (terrain / "tile.tif").exists()
    assert (osm / "query.json").exists()
    assert (elevation / "points.json").exists()


def test_clear_cache_can_clear_osm_and_elevation_cache(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    outputs = tmp_path / "outputs"
    cache = tmp_path / "cache"
    terrain = cache / "terrain_tiles"
    osm = cache / "osm"
    elevation = cache / "elevation"
    for path in (jobs, outputs, terrain, osm, elevation):
        path.mkdir(parents=True)
    (terrain / "tile.tif").write_text("terrain", encoding="utf-8")
    (osm / "query.json").write_text("{}", encoding="utf-8")
    (elevation / "points.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "JOBS_DIR", jobs)
    monkeypatch.setattr(main, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(main, "CACHE_DIR", cache)

    result = main.clear_cache({"generated": False, "terrain": False, "osm": True, "elevation": True})

    assert "osm" in result["cleared"]
    assert "elevation" in result["cleared"]
    assert not any(osm.iterdir())
    assert not any(elevation.iterdir())
    assert (terrain / "tile.tif").exists()


def test_job_downloads_use_summary_file_names():
    summary = {
        "files": {
            "3mf": "UW_Campus.3mf",
            "glb": "UW_Campus.glb",
            "stl": "UW_Campus.stl",
            "attribution": "ATTRIBUTION.txt",
            "chunks_zip": "UW_Campus_chunks.zip",
            "chunks_manifest": "UW_Campus_chunks_manifest.json",
            "project": "UW_Campus_project.json",
        }
    }

    downloads = main.job_downloads("abc123", summary)

    assert downloads["3mf"].endswith("/UW_Campus.3mf")
    assert downloads["glb"].endswith("/UW_Campus.glb")
    assert downloads["stl"].endswith("/UW_Campus.stl")
    assert downloads["chunks"].endswith("/UW_Campus_chunks.zip")
    assert downloads["chunks_manifest"].endswith("/UW_Campus_chunks_manifest.json")
    assert downloads["project"].endswith("/UW_Campus_project.json")


def test_create_job_parses_uploaded_route_file(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    outputs = tmp_path / "outputs"
    cache = tmp_path / "cache"
    for path in (jobs, outputs, cache):
        path.mkdir(parents=True)

    captured = {}

    def fake_submit_job(job_id, fn, params_data, dem_path):
        captured["job_id"] = job_id
        captured["params_data"] = params_data
        captured["dem_path"] = dem_path

    monkeypatch.setattr(main, "JOBS_DIR", jobs)
    monkeypatch.setattr(main, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(main, "CACHE_DIR", cache)
    monkeypatch.setattr(main, "submit_job", fake_submit_job)

    gpx = b"""<?xml version="1.0"?>
    <gpx version="1.1"><trk><trkseg>
      <trkpt lat="47.6200" lon="-122.3500" />
      <trkpt lat="47.6210" lon="-122.3490" />
    </trkseg></trk></gpx>"""
    route_file = UploadFile(filename="walk.gpx", file=BytesIO(gpx))
    params = {
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "include_route": True,
    }

    result = asyncio.run(main.create_job(params=json.dumps(params), dem_file=None, route_file=route_file))

    assert result["job_id"] == captured["job_id"]
    assert captured["dem_path"] is None
    assert captured["params_data"]["route_name"] == "walk.gpx"
    assert captured["params_data"]["route_segments"] == [[[47.62, -122.35], [47.621, -122.349]]]
    assert (jobs / captured["job_id"] / "route.gpx").exists()


def test_cancel_running_job_marks_cancelling(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    outputs = tmp_path / "outputs"
    cache = tmp_path / "cache"
    for path in (jobs, outputs, cache):
        path.mkdir(parents=True)

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "JOBS_DIR", jobs)
    monkeypatch.setattr(main, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(main, "CACHE_DIR", cache)
    with main.ACTIVE_JOBS_LOCK:
        main.ACTIVE_JOBS.clear()
        main.ACTIVE_JOBS.add("job123")
    with main.JOB_FUTURES_LOCK:
        main.JOB_FUTURES.clear()
        main.JOB_FUTURES["job123"] = FakeFuture(can_cancel=False)

    main.write_status("job123", {"job_id": "job123", "status": "running", "message": "Loading OpenStreetMap data", "progress": 0.28})

    result = main.cancel_job("job123")

    assert result["status"] == "cancelling"
    assert result["cancel_requested"] is True
    assert (jobs / "job123" / "cancel.requested").exists()
    assert "job123" in main.ACTIVE_JOBS
    with main.ACTIVE_JOBS_LOCK:
        main.ACTIVE_JOBS.clear()
    with main.JOB_FUTURES_LOCK:
        main.JOB_FUTURES.clear()


def test_cancel_queued_job_marks_cancelled_and_removes_outputs(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    outputs = tmp_path / "outputs"
    cache = tmp_path / "cache"
    for path in (jobs, outputs / "job456", cache):
        path.mkdir(parents=True)
    (outputs / "job456" / "partial.3mf").write_text("partial", encoding="utf-8")

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "JOBS_DIR", jobs)
    monkeypatch.setattr(main, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(main, "CACHE_DIR", cache)
    with main.ACTIVE_JOBS_LOCK:
        main.ACTIVE_JOBS.clear()
        main.ACTIVE_JOBS.add("job456")
    with main.JOB_FUTURES_LOCK:
        main.JOB_FUTURES.clear()
        main.JOB_FUTURES["job456"] = FakeFuture(can_cancel=True)

    main.write_status("job456", {"job_id": "job456", "status": "queued", "message": "Queued", "progress": 0.0})

    result = main.cancel_job("job456")

    assert result["status"] == "cancelled"
    assert result["cancel_requested"] is True
    assert not (outputs / "job456").exists()
    assert "job456" not in main.ACTIVE_JOBS
    with main.JOB_FUTURES_LOCK:
        main.JOB_FUTURES.clear()
