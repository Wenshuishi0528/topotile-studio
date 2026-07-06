from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import math
import time
from typing import Any, Callable, Iterable
import json
import requests

from shapely.geometry import LineString, MultiLineString, Polygon, MultiPolygon, GeometryCollection, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid

from .cancel import CancelCheck, check_cancel
from .geo import LocalProjection

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
FALLBACK_OVERPASS_URLS = [
    DEFAULT_OVERPASS_URL,
    "https://overpass.private.coffee/api/interpreter",
]
OVERPASS_USER_AGENT = "OSM-DEM-3MF-Modeler/0.1 (local desktop 3D-printing app)"
TILED_FETCH_MAX_DEPTH = 2
TILED_FETCH_ATTEMPTS = 2
OSM_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "osm"
AREA_INFILL_LANDUSE_RE = (
    "residential|industrial|commercial|retail|garages|depot|railway|brownfield|construction|"
    "military|education|institutional|civic_admin|religious"
)
AREA_INFILL_AMENITY_RE = (
    "hospital|clinic|school|university|college|kindergarten|public_building|townhall|police|"
    "fire_station|prison|marketplace|place_of_worship|community_centre"
)
AREA_INFILL_TOURISM_RE = "theme_park|attraction|museum|hotel"
AREA_INFILL_HISTORIC_RE = "district|yes|archaeological_site|monument|castle"
AREA_INFILL_MAN_MADE_RE = "works|industrial"
RAILWAY_LINE_RE = "rail|narrow_gauge|light_rail|tram|monorail|subway"
RAILWAY_STATION_RE = "station|halt|subway_entrance|tram_stop"
POWER_LINE_RE = "line|minor_line"
POWER_SUPPORT_RE = "tower|pole"
POWER_AREA_RE = "plant"


class OverpassFetchError(RuntimeError):
    pass


@dataclass(slots=True)
class OSMFeature:
    layer: str
    geometry_m: BaseGeometry
    tags: dict[str, str]
    osm_id: str


Progress = Callable[[str, float], None]


def overpass_query(south: float, west: float, north: float, east: float, timeout_s: int = 90) -> str:
    bbox = f"{south},{west},{north},{east}"
    return f"""
[out:json][timeout:{int(timeout_s)}];
(
  way["building"]({bbox});
  way["building:part"]({bbox});
  relation["building"]({bbox});
  relation["building:part"]({bbox});
  way["highway"]({bbox});
  way["railway"~"{RAILWAY_LINE_RE}"]({bbox});
  way["railway"~"{RAILWAY_STATION_RE}"]({bbox});
  relation["railway"~"{RAILWAY_STATION_RE}"]({bbox});
  node["railway"~"{RAILWAY_STATION_RE}"]({bbox});
  way["public_transport"="station"]({bbox});
  relation["public_transport"="station"]({bbox});
  node["public_transport"="station"]({bbox});
  way["station"~"subway|train|rail|light_rail"]({bbox});
  relation["station"~"subway|train|rail|light_rail"]({bbox});
  node["station"~"subway|train|rail|light_rail"]({bbox});
  way["power"~"{POWER_LINE_RE}"]({bbox});
  relation["power"~"{POWER_LINE_RE}"]({bbox});
  node["power"~"{POWER_SUPPORT_RE}"]({bbox});
  way["power"~"{POWER_SUPPORT_RE}"]({bbox});
  way["power"~"{POWER_AREA_RE}"]({bbox});
  relation["power"~"{POWER_AREA_RE}"]({bbox});
  way["amenity"="parking"]({bbox});
  relation["amenity"="parking"]({bbox});
  way["aeroway"~"runway|taxiway|apron"]({bbox});
  relation["aeroway"~"runway|taxiway|apron"]({bbox});
  way["natural"="water"]({bbox});
  way["natural"~"bay|strait"]({bbox});
  way["natural"="coastline"]({bbox});
  way["water"]({bbox});
  way["waterway"]({bbox});
  relation["natural"="water"]({bbox});
  relation["natural"~"bay|strait"]({bbox});
  relation["water"]({bbox});
  relation["waterway"="riverbank"]({bbox});
  way["landuse"~"forest|grass|meadow|recreation_ground|village_green|cemetery|allotments|orchard|vineyard|flowerbed|plant_nursery"]({bbox});
  way["leisure"~"park|garden|golf_course|playground|sports_centre|pitch|nature_reserve"]({bbox});
  way["landcover"~"grass|trees|wood|greenery|shrubs|herbaceous|flowerbed|forest|meadow"]({bbox});
  way["natural"~"wood|grassland|scrub|heath|wetland|shrubbery"]({bbox});
  way["barrier"~"hedge|planter"]({bbox});
  way["man_made"="planter"]({bbox});
  way["boundary"="protected_area"]({bbox});
  way["amenity"="grave_yard"]({bbox});
  relation["landuse"~"forest|grass|meadow|recreation_ground|village_green|cemetery|allotments|orchard|vineyard|flowerbed|plant_nursery"]({bbox});
  relation["leisure"~"park|garden|golf_course|playground|sports_centre|pitch|nature_reserve"]({bbox});
  relation["landcover"~"grass|trees|wood|greenery|shrubs|herbaceous|flowerbed|forest|meadow"]({bbox});
  relation["natural"~"wood|grassland|scrub|heath|wetland|shrubbery"]({bbox});
  relation["barrier"~"hedge|planter"]({bbox});
  relation["man_made"="planter"]({bbox});
  relation["boundary"="protected_area"]({bbox});
  relation["amenity"="grave_yard"]({bbox});
  way["landuse"~"{AREA_INFILL_LANDUSE_RE}"]({bbox});
  relation["landuse"~"{AREA_INFILL_LANDUSE_RE}"]({bbox});
  way["amenity"~"{AREA_INFILL_AMENITY_RE}"]({bbox});
  relation["amenity"~"{AREA_INFILL_AMENITY_RE}"]({bbox});
  way["healthcare"]({bbox});
  relation["healthcare"]({bbox});
  way["tourism"~"{AREA_INFILL_TOURISM_RE}"]({bbox});
  relation["tourism"~"{AREA_INFILL_TOURISM_RE}"]({bbox});
  way["historic"~"{AREA_INFILL_HISTORIC_RE}"]({bbox});
  relation["historic"~"{AREA_INFILL_HISTORIC_RE}"]({bbox});
  way["place"="city_block"]({bbox});
  relation["place"="city_block"]({bbox});
  way["man_made"~"{AREA_INFILL_MAN_MADE_RE}"]({bbox});
  relation["man_made"~"{AREA_INFILL_MAN_MADE_RE}"]({bbox});
  way["office"]({bbox});
  relation["office"]({bbox});
);
out body geom;
""".strip()


def water_overpass_query(south: float, west: float, north: float, east: float, timeout_s: int = 120) -> str:
    bbox = f"{south},{west},{north},{east}"
    return f"""
[out:json][timeout:{int(timeout_s)}];
(
  way["natural"="water"]({bbox});
  way["natural"~"bay|strait"]({bbox});
  way["natural"="coastline"]({bbox});
  way["water"]({bbox});
  way["waterway"]({bbox});
  relation["natural"="water"]({bbox});
  relation["natural"~"bay|strait"]({bbox});
  relation["water"]({bbox});
  relation["waterway"="riverbank"]({bbox});
);
(._;>;);
out body geom;
""".strip()


def _osm_cache_key_for_query(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def _osm_cache_key(south: float, west: float, north: float, east: float) -> str:
    query = overpass_query(south, west, north, east, timeout_s=0)
    return _osm_cache_key_for_query(query)


def _osm_cache_path(key: str) -> Path:
    return OSM_CACHE_DIR / f"{key}.json"


def _load_osm_cache(key: str) -> dict[str, Any] | None:
    path = _osm_cache_path(key)
    if not path.exists() or path.stat().st_size <= 0:
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            cached = json.load(f)
    except (OSError, ValueError):
        return None
    return cached if isinstance(cached, dict) else None


def _save_osm_cache(key: str, data: dict[str, Any]) -> None:
    OSM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _osm_cache_path(key)
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f)
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _fetch_overpass_query_json(
    query: str,
    cache_key: str,
    overpass_url: str,
    read_timeout_s: int,
    cancel_check: CancelCheck | None,
) -> dict[str, Any]:
    cached = _load_osm_cache(cache_key)
    if cached is not None:
        check_cancel(cancel_check)
        return cached

    urls = [overpass_url]
    if overpass_url == DEFAULT_OVERPASS_URL:
        urls.extend(url for url in FALLBACK_OVERPASS_URLS if url not in urls)

    errors: list[str] = []
    headers = {
        "User-Agent": OVERPASS_USER_AGENT,
        "Accept": "application/json",
    }
    for url in urls:
        check_cancel(cancel_check)
        try:
            response = requests.post(url, data={"data": query}, headers=headers, timeout=(10, read_timeout_s))
            check_cancel(cancel_check)
            if response.status_code >= 400:
                excerpt = " ".join(response.text.split())[:320]
                errors.append(f"{url}: HTTP {response.status_code} {excerpt}")
                continue
            data = response.json()
            if isinstance(data, dict):
                _save_osm_cache(cache_key, data)
            return data
        except requests.RequestException as exc:
            errors.append(f"{url}: {exc}")
        except ValueError as exc:
            errors.append(f"{url}: invalid JSON response: {exc}")

    detail = "; ".join(errors) if errors else "no response details"
    raise OverpassFetchError(
        "OpenStreetMap data download failed. The public Overpass service rejected the request "
        "or did not respond. No API key is required for normal use; try a smaller map selection "
        f"or retry later. Details: {detail}"
    )


def fetch_osm_json(
    south: float,
    west: float,
    north: float,
    east: float,
    overpass_url: str = DEFAULT_OVERPASS_URL,
    overpass_timeout_s: int = 90,
    read_timeout_s: int = 120,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    check_cancel(cancel_check)
    query = overpass_query(south, west, north, east, timeout_s=overpass_timeout_s)
    cache_key = _osm_cache_key(south, west, north, east)
    return _fetch_overpass_query_json(query, cache_key, overpass_url, read_timeout_s, cancel_check)


def fetch_water_osm_json(
    south: float,
    west: float,
    north: float,
    east: float,
    overpass_url: str = DEFAULT_OVERPASS_URL,
    overpass_timeout_s: int = 120,
    read_timeout_s: int = 150,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    check_cancel(cancel_check)
    query = water_overpass_query(south, west, north, east, timeout_s=overpass_timeout_s)
    cache_query = water_overpass_query(south, west, north, east, timeout_s=0)
    cache_key = _osm_cache_key_for_query(cache_query)
    return _fetch_overpass_query_json(query, cache_key, overpass_url, read_timeout_s, cancel_check)


def _bbox_tiles(
    south: float,
    west: float,
    north: float,
    east: float,
    tile_size_km: float,
) -> list[tuple[float, float, float, float]]:
    mid_lat = (south + north) / 2.0
    lat_m = 111_320.0
    lon_m = max(1.0, 111_320.0 * math.cos(math.radians(mid_lat)))
    height_m = max(1.0, (north - south) * lat_m)
    width_m = max(1.0, (east - west) * lon_m)
    target_m = max(500.0, tile_size_km * 1000.0)
    rows = max(1, int(math.ceil(height_m / target_m)))
    cols = max(1, int(math.ceil(width_m / target_m)))
    lat_step = (north - south) / rows
    lon_step = (east - west) / cols
    tiles: list[tuple[float, float, float, float]] = []
    for row in range(rows):
        ts = south + row * lat_step
        tn = north if row == rows - 1 else south + (row + 1) * lat_step
        for col in range(cols):
            tw = west + col * lon_step
            te = east if col == cols - 1 else west + (col + 1) * lon_step
            tiles.append((ts, tw, tn, te))
    return tiles


def _split_bbox(south: float, west: float, north: float, east: float) -> list[tuple[float, float, float, float]]:
    mid_lat = (south + north) / 2.0
    mid_lon = (west + east) / 2.0
    return [
        (south, west, mid_lat, mid_lon),
        (south, mid_lon, mid_lat, east),
        (mid_lat, west, north, mid_lon),
        (mid_lat, mid_lon, north, east),
    ]


def _element_geometry_score(element: dict[str, Any]) -> int:
    score = len(element.get("geometry") or [])
    for member in element.get("members") or []:
        score += len(member.get("geometry") or [])
    if element.get("tags"):
        score += 1
    return score


def _merge_best_elements(target: dict[tuple[str, str], dict[str, Any]], elements: Iterable[dict[str, Any]]) -> None:
    for element in elements:
        key = (str(element.get("type", "")), str(element.get("id", "")))
        if not key[0] or not key[1]:
            continue
        existing = target.get(key)
        if existing is None or _element_geometry_score(element) > _element_geometry_score(existing):
            target[key] = element


def merge_osm_json(primary: dict[str, Any], supplemental: dict[str, Any]) -> dict[str, Any]:
    elements_by_id: dict[tuple[str, str], dict[str, Any]] = {}
    _merge_best_elements(elements_by_id, primary.get("elements", []))
    _merge_best_elements(elements_by_id, supplemental.get("elements", []))
    merged = dict(primary)
    merged["elements"] = list(elements_by_id.values())
    merged["supplemental_element_count"] = len(supplemental.get("elements", []))
    merged["merged_element_count"] = len(merged["elements"])
    return merged


def _fetch_tile_recursive(
    south: float,
    west: float,
    north: float,
    east: float,
    overpass_url: str,
    depth: int = 0,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    check_cancel(cancel_check)
    last_error = ""
    for attempt in range(TILED_FETCH_ATTEMPTS):
        check_cancel(cancel_check)
        try:
            return fetch_osm_json(
                south,
                west,
                north,
                east,
                overpass_url,
                overpass_timeout_s=45,
                read_timeout_s=70,
                cancel_check=cancel_check,
            )
        except OverpassFetchError as exc:
            last_error = str(exc)
            if attempt + 1 < TILED_FETCH_ATTEMPTS:
                check_cancel(cancel_check)
                time.sleep(0.8 + attempt * 0.8)
                check_cancel(cancel_check)

    if depth >= TILED_FETCH_MAX_DEPTH:
        raise OverpassFetchError(last_error or "OpenStreetMap tile download failed.")

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    child_errors: list[str] = []
    for child in _split_bbox(south, west, north, east):
        check_cancel(cancel_check)
        try:
            child_data = _fetch_tile_recursive(
                *child,
                overpass_url=overpass_url,
                depth=depth + 1,
                cancel_check=cancel_check,
            )
        except OverpassFetchError as exc:
            child_errors.append(str(exc))
            continue
        _merge_best_elements(merged, child_data.get("elements", []))
        check_cancel(cancel_check)

    if child_errors:
        detail = "; ".join(child_errors[:4])
        raise OverpassFetchError(
            "OpenStreetMap tile still failed after automatic subdivision. "
            f"Original error: {last_error}. Subtile errors: {detail}"
        )
    return {
        "version": 0.6,
        "generator": "TopoTile Studio / 3D地图工坊 recursive tiled Overpass fetch",
        "elements": list(merged.values()),
    }


def fetch_osm_json_tiled(
    south: float,
    west: float,
    north: float,
    east: float,
    overpass_url: str = DEFAULT_OVERPASS_URL,
    tile_size_km: float = 2.5,
    progress: Progress | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    check_cancel(cancel_check)
    tiles = _bbox_tiles(south, west, north, east, tile_size_km)
    elements_by_id: dict[tuple[str, str], dict[str, Any]] = {}
    errors: list[str] = []

    for index, (ts, tw, tn, te) in enumerate(tiles, start=1):
        check_cancel(cancel_check)
        if progress:
            progress(f"Loading OpenStreetMap tile {index}/{len(tiles)}", (index - 1) / len(tiles))
        try:
            data = _fetch_tile_recursive(ts, tw, tn, te, overpass_url, cancel_check=cancel_check)
        except OverpassFetchError as exc:
            if len(tiles) == 1:
                raise
            errors.append(f"tile {index}/{len(tiles)}: {exc}")
            continue
        _merge_best_elements(elements_by_id, data.get("elements", []))
        check_cancel(cancel_check)
        time.sleep(0.15)
        check_cancel(cancel_check)

    elements = list(elements_by_id.values())
    if progress:
        progress(f"Loaded {len(elements)} unique OpenStreetMap elements from {len(tiles)} tiles", 1.0)
    if errors:
        detail = "; ".join(errors[:6])
        raise OverpassFetchError(
            "OpenStreetMap tiled download did not complete, so generation stopped to avoid missing "
            f"buildings, roads, or green areas. Details: {detail}"
        )
    return {
        "version": 0.6,
        "generator": "TopoTile Studio / 3D地图工坊 tiled Overpass fetch",
        "elements": elements,
        "tile_count": len(tiles),
        "tile_errors": errors,
    }


def load_osm_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_osm_json(data: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def classify(tags: dict[str, Any], is_closed: bool) -> str | None:
    if "building" in tags or "building:part" in tags:
        return "building"
    if _is_subway_station(tags):
        return "subway_station"
    if _is_rail_station(tags):
        return "rail_station"
    railway = tags.get("railway")
    if railway == "subway":
        return "subway_line"
    if railway in {"rail", "narrow_gauge", "light_rail", "tram", "monorail"}:
        return "rail_line"
    power = str(tags.get("power", "")).lower()
    if power == "line":
        return "power_line"
    if power == "minor_line":
        return "minor_power_line"
    if power in {"tower", "pole"}:
        return "power_tower"
    if is_closed and power == "plant":
        return "power_plant"
    highway = tags.get("highway")
    if highway:
        return "road"
    if _is_surface_parking(tags):
        return "parking"
    if tags.get("aeroway") in {"runway", "taxiway", "apron"}:
        return "airport"
    if tags.get("natural") == "coastline":
        return "coastline"
    if tags.get("natural") in {"water", "bay", "strait"} or "water" in tags:
        return "water"
    if tags.get("waterway") in {"river", "stream", "canal", "ditch", "drain", "riverbank"}:
        return "water"
    if is_closed and tags.get("barrier") in {"hedge", "planter"}:
        return "green"
    if is_closed and tags.get("man_made") == "planter":
        return "green"
    if tags.get("landuse") in {
        "forest", "grass", "meadow", "recreation_ground", "village_green", "cemetery", "allotments",
        "orchard", "vineyard", "flowerbed", "plant_nursery"
    }:
        return "green"
    if tags.get("leisure") in {"park", "garden", "golf_course", "playground", "sports_centre", "pitch", "nature_reserve"}:
        return "green"
    if tags.get("landcover") in {"grass", "trees", "wood", "greenery", "shrubs", "herbaceous", "flowerbed", "forest", "meadow"}:
        return "green"
    if tags.get("natural") in {"wood", "grassland", "scrub", "heath", "shrubbery"}:
        return "green"
    if tags.get("amenity") == "grave_yard":
        return "green"
    if tags.get("natural") == "wetland" or tags.get("boundary") == "protected_area":
        return "green"
    if _is_area_infill(tags, is_closed):
        return "area_infill"
    return None


def _is_subway_station(tags: dict[str, Any]) -> bool:
    railway = str(tags.get("railway", "")).lower()
    station = str(tags.get("station", "")).lower()
    public_transport = str(tags.get("public_transport", "")).lower()
    if railway == "subway_entrance":
        return True
    if station == "subway":
        return True
    if railway == "station" and (
        tags.get("subway") == "yes" or tags.get("railway:station_category") == "subway"
    ):
        return True
    return public_transport == "station" and (station == "subway" or tags.get("subway") == "yes")


def _is_rail_station(tags: dict[str, Any]) -> bool:
    railway = str(tags.get("railway", "")).lower()
    station = str(tags.get("station", "")).lower()
    public_transport = str(tags.get("public_transport", "")).lower()
    if railway in {"station", "halt", "tram_stop"}:
        return True
    if public_transport == "station" and station in {"train", "rail", "light_rail"}:
        return True
    if public_transport == "station" and (
        tags.get("train") == "yes" or tags.get("rail") == "yes" or tags.get("light_rail") == "yes"
    ):
        return True
    return False


def _is_surface_parking(tags: dict[str, Any]) -> bool:
    if tags.get("amenity") != "parking":
        return False
    if tags.get("underground") == "yes" or tags.get("covered") == "yes" or tags.get("location") == "underground":
        return False
    parking = str(tags.get("parking", "")).replace("_", "-")
    excluded = {"multi-storey", "underground", "rooftop", "garage-boxes", "carports"}
    if parking in excluded:
        return False
    if str(tags.get("parking:condition", "")).lower() == "covered":
        return False
    return True


def _is_area_infill(tags: dict[str, Any], is_closed: bool) -> bool:
    if not is_closed:
        return False
    if tags.get("area") == "no":
        return False
    if tags.get("landuse") in {
        "residential", "industrial", "commercial", "retail", "garages", "depot", "railway",
        "brownfield", "construction", "military", "education", "institutional", "civic_admin",
        "religious",
    }:
        return True
    if tags.get("amenity") in {
        "hospital", "clinic", "school", "university", "college", "kindergarten", "public_building",
        "townhall", "police", "fire_station", "prison", "marketplace", "place_of_worship",
        "community_centre",
    }:
        return True
    if "healthcare" in tags:
        return True
    if tags.get("tourism") in {"theme_park", "attraction", "museum", "hotel"}:
        return True
    if tags.get("historic") in {"district", "yes", "archaeological_site", "monument", "castle"}:
        return True
    if tags.get("place") == "city_block":
        return True
    if tags.get("man_made") in {"works", "industrial"}:
        return True
    if "office" in tags:
        return True
    return False


def _closed_way_should_be_polygon(layer: str, tags: dict[str, str], is_closed: bool) -> bool:
    if not is_closed:
        return False
    if layer != "water":
        return layer in {
            "building", "green", "parking", "airport", "area_infill",
            "rail_station", "subway_station", "power_plant",
        }
    if str(tags.get("area", "")).lower() == "yes":
        return True
    if tags.get("waterway") == "riverbank":
        return True
    if tags.get("natural") in {"water", "bay", "strait"}:
        return True
    if "water" in tags:
        return True
    return False


def _lonlat_from_geometry(raw_geom: list[dict[str, Any]]) -> list[tuple[float, float]]:
    return [(float(p["lon"]), float(p["lat"])) for p in raw_geom if "lon" in p and "lat" in p]


def _is_closed_lonlat(coords: list[tuple[float, float]]) -> bool:
    if len(coords) < 4:
        return False
    a = coords[0]
    b = coords[-1]
    return abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9


def _safe_geom(geom: BaseGeometry) -> BaseGeometry | None:
    if geom.is_empty:
        return None
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.is_empty:
        return None
    if isinstance(geom, GeometryCollection):
        polys = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon)) and not g.is_empty]
        lines = [g for g in geom.geoms if isinstance(g, LineString) and not g.is_empty]
        if polys:
            return MultiPolygon([p for g in polys for p in (g.geoms if isinstance(g, MultiPolygon) else [g])])
        if lines:
            return lines[0]
        return None
    return geom


def _line_geoms(geom: BaseGeometry) -> list[LineString]:
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return [line for line in geom.geoms if not line.is_empty]
    if isinstance(geom, GeometryCollection):
        lines: list[LineString] = []
        for part in geom.geoms:
            lines.extend(_line_geoms(part))
        return lines
    return []


def _clip_geom(geom: BaseGeometry, clip: Polygon) -> BaseGeometry | None:
    geom = _safe_geom(geom)
    if geom is None:
        return None
    try:
        geom = geom.intersection(clip)
    except Exception:
        return None
    return _safe_geom(geom)


def _member_raw_geometry(
    member: dict[str, Any],
    way_geometries: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    raw_geom = member.get("geometry") or []
    if raw_geom:
        return raw_geom
    if not way_geometries:
        return []
    ref = member.get("ref")
    if ref is None:
        return []
    return way_geometries.get(str(ref), [])


def _relation_member_lines(
    element: dict[str, Any],
    projection: LocalProjection,
    way_geometries: dict[str, list[dict[str, Any]]] | None = None,
) -> list[LineString]:
    lines: list[LineString] = []
    for member in element.get("members") or []:
        if member.get("type") != "way":
            continue
        raw_geom = _member_raw_geometry(member, way_geometries)
        lonlat = _lonlat_from_geometry(raw_geom)
        if len(lonlat) < 2:
            continue
        local_coords = [projection.lonlat_to_local(lon, lat) for lon, lat in lonlat]
        try:
            line = LineString(local_coords)
        except Exception:
            continue
        if not line.is_empty:
            lines.append(line)
    return lines


def _relation_member_lines_by_role(
    element: dict[str, Any],
    projection: LocalProjection,
    way_geometries: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[list[LineString], list[LineString], list[LineString]]:
    outer: list[LineString] = []
    inner: list[LineString] = []
    all_lines: list[LineString] = []
    for member in element.get("members") or []:
        if member.get("type") != "way":
            continue
        raw_geom = _member_raw_geometry(member, way_geometries)
        lonlat = _lonlat_from_geometry(raw_geom)
        if len(lonlat) < 2:
            continue
        local_coords = [projection.lonlat_to_local(lon, lat) for lon, lat in lonlat]
        try:
            line = LineString(local_coords)
        except Exception:
            continue
        if line.is_empty:
            continue
        all_lines.append(line)
        if member.get("role") == "inner":
            inner.append(line)
        else:
            outer.append(line)
    return outer, inner, all_lines


def _polygonize_lines(lines: list[LineString]) -> BaseGeometry | None:
    if not lines:
        return None
    try:
        polygons = list(polygonize(unary_union(lines)))
    except Exception:
        return None
    if not polygons:
        return None
    try:
        return unary_union(polygons)
    except Exception:
        return None


def _polygons_from_relation(
    element: dict[str, Any],
    projection: LocalProjection,
    clip: Polygon,
    way_geometries: dict[str, list[dict[str, Any]]] | None = None,
) -> list[Polygon]:
    outer_lines, inner_lines, all_lines = _relation_member_lines_by_role(element, projection, way_geometries)
    if not all_lines:
        return []
    geom = _polygonize_lines(outer_lines) or _polygonize_lines(all_lines)
    if geom is None:
        return []
    inner_geom = _polygonize_lines(inner_lines)
    if inner_geom is not None and not inner_geom.is_empty:
        try:
            geom = geom.difference(inner_geom)
        except Exception:
            pass
    geom = _clip_geom(geom, clip)
    if geom is None:
        return []
    return [poly for poly in _iter_polygons_for_osm(geom)]


def _nearest_coastline_side(point: Point, coastlines: list[LineString]) -> float | None:
    best_distance = float("inf")
    best_cross: float | None = None
    px, py = point.x, point.y
    for line in coastlines:
        coords = list(line.coords)
        for p0, p1 in zip(coords, coords[1:]):
            x0, y0 = p0
            x1, y1 = p1
            dx = x1 - x0
            dy = y1 - y0
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq <= 1e-12:
                continue
            t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / seg_len_sq))
            qx = x0 + t * dx
            qy = y0 + t * dy
            distance = (px - qx) ** 2 + (py - qy) ** 2
            if distance < best_distance:
                best_distance = distance
                best_cross = dx * (py - y0) - dy * (px - x0)
    return best_cross


def _coastline_water_polygons(coastlines: list[LineString], clip: Polygon) -> list[Polygon]:
    clipped_lines: list[LineString] = []
    for line in coastlines:
        geom = _clip_geom(line, clip)
        if geom is not None:
            clipped_lines.extend(_line_geoms(geom))
    if not clipped_lines:
        return []
    try:
        linework = unary_union(clipped_lines + [LineString(clip.exterior.coords)])
        candidates = list(polygonize(linework))
    except Exception:
        return []

    water_polys: list[Polygon] = []
    for poly in candidates:
        if poly.is_empty or poly.area <= 1e-6:
            continue
        side = _nearest_coastline_side(poly.representative_point(), clipped_lines)
        # OSM coastline convention keeps land on the left and water on the right.
        if side is not None and side < 0:
            clipped = _clip_geom(poly, clip)
            if clipped is not None:
                water_polys.extend(list(_iter_polygons_for_osm(clipped)))
    return water_polys


def _iter_polygons_for_osm(geom: BaseGeometry) -> Iterable[Polygon]:
    if geom.is_empty:
        return
    if isinstance(geom, Polygon):
        yield geom
    elif isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            yield poly
    elif isinstance(geom, GeometryCollection):
        for part in geom.geoms:
            yield from _iter_polygons_for_osm(part)


def parse_osm_features(osm_json: dict[str, Any], projection: LocalProjection) -> list[OSMFeature]:
    features: list[OSMFeature] = []
    clip = projection.bbox_polygon_m
    coastlines: list[LineString] = []
    elements = osm_json.get("elements", [])
    way_geometries = {
        str(element.get("id")): element.get("geometry") or []
        for element in elements
        if element.get("type") == "way" and element.get("id") is not None and len(element.get("geometry") or []) >= 2
    }

    for element in elements:
        element_type = element.get("type")
        tags = {str(k): str(v) for k, v in (element.get("tags") or {}).items()}
        if element_type == "relation":
            layer = classify(tags, is_closed=True)
            if layer in {
                "green", "building", "parking", "airport", "area_infill",
                "rail_station", "subway_station", "power_plant",
            } or (
                layer == "water" and _closed_way_should_be_polygon("water", tags, is_closed=True)
            ):
                for poly in _polygons_from_relation(element, projection, clip, way_geometries):
                    features.append(OSMFeature(layer=layer, geometry_m=poly, tags=tags, osm_id=f"relation/{element.get('id', 'unknown')}"))
            continue

        if element_type == "node":
            layer = classify(tags, is_closed=False)
            if layer not in {"rail_station", "subway_station", "power_tower"}:
                continue
            try:
                point = Point(*projection.lonlat_to_local(float(element["lon"]), float(element["lat"])))
            except Exception:
                continue
            if not clip.covers(point):
                continue
            features.append(OSMFeature(layer=layer, geometry_m=point, tags=tags, osm_id=f"node/{element.get('id', 'unknown')}"))
            continue

        if element_type != "way":
            continue
        raw_geom = element.get("geometry") or []
        if len(raw_geom) < 2:
            continue
        lonlat = _lonlat_from_geometry(raw_geom)
        if len(lonlat) < 2:
            continue
        is_closed = _is_closed_lonlat(lonlat)
        layer = classify(tags, is_closed)
        if not layer:
            continue

        local_coords = [projection.lonlat_to_local(lon, lat) for lon, lat in lonlat]
        try:
            if layer == "coastline":
                coastlines.append(LineString(local_coords))
                continue
            if _closed_way_should_be_polygon(layer, tags, is_closed):
                geom: BaseGeometry = Polygon(local_coords)
            else:
                geom = LineString(local_coords)
        except Exception:
            continue

        geom = _safe_geom(geom)
        if geom is None:
            continue
        try:
            geom = geom.intersection(clip)
        except Exception:
            continue
        geom = _safe_geom(geom)
        if geom is None or geom.is_empty:
            continue

        features.append(OSMFeature(layer=layer, geometry_m=geom, tags=tags, osm_id=f"way/{element.get('id', 'unknown')}"))

    for poly in _coastline_water_polygons(coastlines, clip):
        features.append(OSMFeature(layer="water", geometry_m=poly, tags={"natural": "coastline", "water": "sea"}, osm_id="coastline"))
    return features


def filter_by_layer(features: Iterable[OSMFeature], layer: str) -> list[OSMFeature]:
    return [f for f in features if f.layer == layer]
