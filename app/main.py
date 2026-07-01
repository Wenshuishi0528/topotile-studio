from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from threading import Lock
from urllib.parse import quote
from uuid import uuid4
import json
import shutil
import traceback
from typing import Any

import requests
from fastapi import Body, FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from city_modeler.cancel import GenerationCancelled
from city_modeler.params import ModelParams
from city_modeler.pipeline import generate_model, generate_sample
from city_modeler.routes import parse_route_text

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
OUTPUTS_DIR = DATA_DIR / "outputs"
CACHE_DIR = DATA_DIR / "cache"
STATIC_DIR = Path(__file__).resolve().parent / "static"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
GEOCODE_USER_AGENT = "TopoTile-Studio/0.1 (local desktop 3D-printing app)"

JOBS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
executor = ThreadPoolExecutor(max_workers=1)
ACTIVE_JOBS: set[str] = set()
ACTIVE_JOBS_LOCK = Lock()
JOB_FUTURES: dict[str, Future] = {}
JOB_FUTURES_LOCK = Lock()

app = FastAPI(title="TopoTile Studio / 3D地图工坊")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def job_dir(job_id: str) -> Path:
    if not job_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in job_id):
        raise HTTPException(status_code=400, detail="Invalid job id")
    return JOBS_DIR / job_id


def status_path(job_id: str) -> Path:
    return job_dir(job_id) / "status.json"


def cancel_path(job_id: str) -> Path:
    return job_dir(job_id) / "cancel.requested"


def write_status(job_id: str, status: dict[str, Any]) -> None:
    jd = job_dir(job_id)
    jd.mkdir(parents=True, exist_ok=True)
    tmp = jd / "status.tmp"
    tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
    tmp.replace(status_path(job_id))


def read_status(job_id: str) -> dict[str, Any]:
    path = status_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(path.read_text(encoding="utf-8"))


def file_url(job_id: str, filename: str) -> str:
    return f"/api/jobs/{job_id}/files/{quote(filename, safe='')}"


def job_downloads(job_id: str, summary: dict[str, Any]) -> dict[str, str]:
    files = summary.get("files") or {}
    downloads = {
        "3mf": file_url(job_id, str(files.get("3mf", "city_model.3mf"))),
        "glb": file_url(job_id, str(files.get("glb", "city_model.glb"))),
        "stl": file_url(job_id, str(files.get("stl", "city_model.stl"))),
        "attribution": file_url(job_id, str(files.get("attribution", "ATTRIBUTION.txt"))),
        "summary": file_url(job_id, "summary.json"),
    }
    if files.get("chunks_zip"):
        downloads["chunks"] = file_url(job_id, str(files["chunks_zip"]))
    if files.get("chunks_manifest"):
        downloads["chunks_manifest"] = file_url(job_id, str(files["chunks_manifest"]))
    if files.get("project"):
        downloads["project"] = file_url(job_id, str(files["project"]))
    return downloads


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def cache_status_payload() -> dict[str, Any]:
    terrain_cache = CACHE_DIR / "terrain_tiles"
    osm_cache = CACHE_DIR / "osm"
    elevation_cache = CACHE_DIR / "elevation"
    return {
        "jobs_bytes": directory_size(JOBS_DIR),
        "outputs_bytes": directory_size(OUTPUTS_DIR),
        "terrain_cache_bytes": directory_size(terrain_cache),
        "osm_cache_bytes": directory_size(osm_cache),
        "elevation_cache_bytes": directory_size(elevation_cache),
        "total_bytes": (
            directory_size(JOBS_DIR)
            + directory_size(OUTPUTS_DIR)
            + directory_size(terrain_cache)
            + directory_size(osm_cache)
            + directory_size(elevation_cache)
        ),
    }


def mark_job_active(job_id: str) -> None:
    with ACTIVE_JOBS_LOCK:
        ACTIVE_JOBS.add(job_id)


def mark_job_inactive(job_id: str) -> None:
    with ACTIVE_JOBS_LOCK:
        ACTIVE_JOBS.discard(job_id)


def active_generated_job_count() -> int:
    with ACTIVE_JOBS_LOCK:
        return len(ACTIVE_JOBS)


def submit_job(job_id: str, fn, *args) -> None:
    mark_job_active(job_id)
    future = executor.submit(fn, job_id, *args)
    with JOB_FUTURES_LOCK:
        JOB_FUTURES[job_id] = future

    def cleanup_future(_future: Future) -> None:
        with JOB_FUTURES_LOCK:
            JOB_FUTURES.pop(job_id, None)
        if _future.cancelled():
            mark_job_inactive(job_id)

    future.add_done_callback(cleanup_future)


def cleanup_job_outputs(job_id: str) -> None:
    shutil.rmtree(OUTPUTS_DIR / job_id, ignore_errors=True)


def request_job_cancel(job_id: str) -> None:
    cancel_path(job_id).write_text("cancel requested\n", encoding="utf-8")


def is_cancel_requested(job_id: str) -> bool:
    return cancel_path(job_id).exists()


def raise_if_cancelled(job_id: str) -> None:
    if is_cancel_requested(job_id):
        raise GenerationCancelled("Cancelled")


def terminal_status(status: str) -> bool:
    return status in {"complete", "failed", "cancelled"}


def completed_at_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def clear_directory_contents(path: Path) -> int:
    root = DATA_DIR.resolve()
    target = path.resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status_code=400, detail="Refusing to clear a path outside the project data directory.")
    before = directory_size(target)
    target.mkdir(parents=True, exist_ok=True)
    for item in target.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            elif item.is_file():
                item.unlink()
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not remove {item.name}: {exc}") from exc
    target.mkdir(parents=True, exist_ok=True)
    return before


def available_job_filenames(job_id: str) -> set[str]:
    filenames = {
        "city_model.3mf",
        "city_model.glb",
        "city_model.stl",
        "city_model_chunks.zip",
        "chunks_manifest.json",
        "ATTRIBUTION.txt",
        "summary.json",
        "error.log",
        "osm_raw.json",
    }
    summary_path = OUTPUTS_DIR / job_id / "summary.json"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            summary = {}
        files = summary.get("files") or {}
        for value in files.values():
            if isinstance(value, str) and value == Path(value).name:
                filenames.add(value)
    return filenames


def run_job(job_id: str, params_data: dict[str, Any], dem_path: str | None) -> None:
    jd = job_dir(job_id)
    out = OUTPUTS_DIR / job_id
    out.mkdir(parents=True, exist_ok=True)

    def progress(message: str, value: float) -> None:
        raise_if_cancelled(job_id)
        current = read_status(job_id)
        current.update({"status": "running", "message": message, "progress": value})
        write_status(job_id, current)

    try:
        raise_if_cancelled(job_id)
        params = ModelParams.from_dict(params_data)
        (jd / "params.json").write_text(json.dumps(params_data, indent=2), encoding="utf-8")
        summary = generate_model(
            params,
            out,
            dem_path=dem_path,
            progress=progress,
            cancel_check=lambda: raise_if_cancelled(job_id),
        )
        raise_if_cancelled(job_id)
        write_status(job_id, {
            "job_id": job_id,
            "status": "complete",
            "message": "Complete",
            "progress": 1.0,
            "completed_at": completed_at_timestamp(),
            "summary": summary,
            "downloads": job_downloads(job_id, summary),
        })
    except GenerationCancelled:
        cleanup_job_outputs(job_id)
        current = read_status(job_id)
        write_status(job_id, {
            "job_id": job_id,
            "status": "cancelled",
            "message": "Cancelled",
            "progress": current.get("progress", 0.0),
            "cancel_requested": True,
        })
    except Exception as exc:
        tb = traceback.format_exc()
        (jd / "error.log").write_text(tb, encoding="utf-8")
        write_status(job_id, {
            "job_id": job_id,
            "status": "failed",
            "message": str(exc),
            "progress": 1.0,
            "error_log": f"/api/jobs/{job_id}/files/error.log",
        })
    finally:
        mark_job_inactive(job_id)


def run_sample_job(job_id: str) -> None:
    out = OUTPUTS_DIR / job_id
    out.mkdir(parents=True, exist_ok=True)
    try:
        raise_if_cancelled(job_id)
        write_status(job_id, {"job_id": job_id, "status": "running", "message": "Preparing built-in offline test model", "progress": 0.2})
        summary = generate_sample(out, cancel_check=lambda: raise_if_cancelled(job_id))
        raise_if_cancelled(job_id)
        write_status(job_id, {
            "job_id": job_id,
            "status": "complete",
            "message": "Complete",
            "progress": 1.0,
            "completed_at": completed_at_timestamp(),
            "summary": summary,
            "downloads": job_downloads(job_id, summary),
        })
    except GenerationCancelled:
        cleanup_job_outputs(job_id)
        current = read_status(job_id)
        write_status(job_id, {
            "job_id": job_id,
            "status": "cancelled",
            "message": "Cancelled",
            "progress": current.get("progress", 0.0),
            "cancel_requested": True,
        })
    except Exception as exc:
        tb = traceback.format_exc()
        (job_dir(job_id) / "error.log").write_text(tb, encoding="utf-8")
        write_status(job_id, {
            "job_id": job_id,
            "status": "failed",
            "message": str(exc),
            "progress": 1.0,
            "error_log": f"/api/jobs/{job_id}/files/error.log",
        })
    finally:
        mark_job_inactive(job_id)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.post("/api/jobs")
async def create_job(
    params: str = Form(...),
    dem_file: UploadFile | None = File(default=None),
    route_file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    try:
        params_data = json.loads(params)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid params JSON: {exc}") from exc

    route_bytes: bytes | None = None
    route_suffix = ""
    if route_file is not None and route_file.filename:
        route_suffix = Path(route_file.filename).suffix.lower()
        if route_suffix not in {".gpx", ".kml"}:
            raise HTTPException(status_code=400, detail="Route upload must be a GPX .gpx or KML .kml file")
        route_bytes = await route_file.read()
        try:
            route_text = route_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Route upload must be UTF-8 encoded GPX/KML XML") from exc
        try:
            params_data["route_segments"] = parse_route_text(route_text, route_file.filename)
            params_data["route_name"] = Path(route_file.filename).name
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid route file: {exc}") from exc

    try:
        ModelParams.from_dict(params_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid params: {exc}") from exc

    job_id = uuid4().hex[:12]
    jd = job_dir(job_id)
    jd.mkdir(parents=True, exist_ok=True)
    dem_path: str | None = None
    if dem_file is not None and dem_file.filename:
        suffix = Path(dem_file.filename).suffix.lower() or ".tif"
        if suffix not in {".tif", ".tiff"}:
            raise HTTPException(status_code=400, detail="DEM upload must be a GeoTIFF .tif or .tiff file")
        dem_path_obj = jd / f"dem{suffix}"
        with dem_path_obj.open("wb") as f:
            shutil.copyfileobj(dem_file.file, f)
        dem_path = str(dem_path_obj)
    if route_bytes is not None and route_file is not None and route_file.filename:
        route_path_obj = jd / f"route{route_suffix}"
        route_path_obj.write_bytes(route_bytes)

    write_status(job_id, {"job_id": job_id, "status": "queued", "message": "Queued", "progress": 0.0})
    submit_job(job_id, run_job, params_data, dem_path)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}


@app.post("/api/sample")
def create_sample_job() -> dict[str, Any]:
    job_id = uuid4().hex[:12]
    job_dir(job_id).mkdir(parents=True, exist_ok=True)
    write_status(job_id, {"job_id": job_id, "status": "queued", "message": "Queued", "progress": 0.0})
    submit_job(job_id, run_sample_job)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}


@app.get("/api/geocode")
def geocode(q: str = Query(..., min_length=2, max_length=220)) -> dict[str, Any]:
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="Enter an address or place name.")
    try:
        response = requests.get(
            NOMINATIM_SEARCH_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "limit": 1,
                "addressdetails": 0,
            },
            headers={
                "User-Agent": GEOCODE_USER_AGENT,
                "Accept": "application/json",
            },
            timeout=(5, 20),
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Address search failed: {exc}") from exc
    if response.status_code >= 400:
        excerpt = " ".join(response.text.split())[:240]
        raise HTTPException(status_code=502, detail=f"Address search service returned HTTP {response.status_code}: {excerpt}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Address search returned invalid JSON.") from exc
    if not isinstance(payload, list) or not payload:
        raise HTTPException(status_code=404, detail="Address not found.")

    item = payload[0]
    try:
        lat = float(item["lat"])
        lon = float(item["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Address search result did not include coordinates.") from exc
    result: dict[str, Any] = {
        "lat": lat,
        "lon": lon,
        "display_name": str(item.get("display_name") or query),
    }
    bbox = item.get("boundingbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        try:
            result["bbox"] = [float(bbox[0]), float(bbox[2]), float(bbox[1]), float(bbox[3])]
        except (TypeError, ValueError):
            pass
    return result


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    return read_status(job_id)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    current = read_status(job_id)
    if terminal_status(str(current.get("status", ""))):
        return current

    request_job_cancel(job_id)
    with JOB_FUTURES_LOCK:
        future = JOB_FUTURES.get(job_id)

    if future is not None and future.cancel():
        cleanup_job_outputs(job_id)
        mark_job_inactive(job_id)
        cancelled = {
            "job_id": job_id,
            "status": "cancelled",
            "message": "Cancelled",
            "progress": current.get("progress", 0.0),
            "cancel_requested": True,
        }
        write_status(job_id, cancelled)
        return cancelled

    current.update({
        "status": "cancelling",
        "message": "Cancelling",
        "cancel_requested": True,
    })
    write_status(job_id, current)
    return current


@app.get("/api/cache/status")
def get_cache_status() -> dict[str, Any]:
    return cache_status_payload()


@app.post("/api/cache/clear")
def clear_cache(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    payload = payload or {}
    include_generated = bool(payload.get("generated", True))
    include_terrain = bool(payload.get("terrain", False))
    include_osm = bool(payload.get("osm", False))
    include_elevation = bool(payload.get("elevation", False))
    before = cache_status_payload()
    removed = 0
    cleared: list[str] = []
    if include_generated:
        active_jobs = active_generated_job_count()
        if active_jobs:
            raise HTTPException(status_code=409, detail=f"Cannot clear generated files while {active_jobs} job is running.")
        removed += clear_directory_contents(JOBS_DIR)
        removed += clear_directory_contents(OUTPUTS_DIR)
        cleared.extend(["jobs", "outputs"])
    if include_terrain:
        removed += clear_directory_contents(CACHE_DIR / "terrain_tiles")
        cleared.append("terrain_tiles")
    if include_osm:
        removed += clear_directory_contents(CACHE_DIR / "osm")
        cleared.append("osm")
    if include_elevation:
        removed += clear_directory_contents(CACHE_DIR / "elevation")
        cleared.append("elevation")
    after = cache_status_payload()
    return {
        "cleared": cleared,
        "removed_bytes": removed,
        "before": before,
        "after": after,
    }


@app.get("/api/jobs/{job_id}/files/{filename}")
def get_job_file(job_id: str, filename: str):
    if filename != Path(filename).name or filename not in available_job_filenames(job_id):
        raise HTTPException(status_code=404, detail="File not available")
    # error.log and params are in job dir; outputs are in output dir.
    p1 = OUTPUTS_DIR / job_id / filename
    p2 = JOBS_DIR / job_id / filename
    path = p1 if p1.exists() else p2
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "application/octet-stream"
    if filename.endswith(".json"):
        media_type = "application/json"
    elif filename.endswith(".txt") or filename.endswith(".log"):
        media_type = "text/plain"
    elif filename.endswith(".glb"):
        media_type = "model/gltf-binary"
    elif filename.endswith(".3mf"):
        media_type = "model/3mf"
    elif filename.endswith(".stl"):
        media_type = "model/stl"
    elif filename.endswith(".zip"):
        media_type = "application/zip"
    return FileResponse(path, media_type=media_type, filename=filename)
