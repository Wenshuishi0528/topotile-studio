from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any, Callable, Iterable
import json
import requests

from shapely.geometry import LineString, MultiLineString, Polygon, MultiPolygon, GeometryCollection, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid

from .geo import LocalProjection

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
FALLBACK_OVERPASS_URLS = [
    DEFAULT_OVERPASS_URL,
    "https://overpass.private.coffee/api/interpreter",
]
OVERPASS_USER_AGENT = "OSM-DEM-3MF-Modeler/0.1 (local desktop 3D-printing app)"


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
  relation["water"]({bbox});
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
);
out body geom;
""".strip()


def fetch_osm_json(
    south: float,
    west: float,
    north: float,
    east: float,
    overpass_url: str = DEFAULT_OVERPASS_URL,
    overpass_timeout_s: int = 90,
    read_timeout_s: int = 120,
) -> dict[str, Any]:
    query = overpass_query(south, west, north, east, timeout_s=overpass_timeout_s)
    urls = [overpass_url]
    if overpass_url == DEFAULT_OVERPASS_URL:
        urls.extend(url for url in FALLBACK_OVERPASS_URLS if url not in urls)

    errors: list[str] = []
    headers = {
        "User-Agent": OVERPASS_USER_AGENT,
        "Accept": "application/json",
    }
    for url in urls:
        try:
            response = requests.post(url, data={"data": query}, headers=headers, timeout=(10, read_timeout_s))
            if response.status_code >= 400:
                excerpt = " ".join(response.text.split())[:320]
                errors.append(f"{url}: HTTP {response.status_code} {excerpt}")
                continue
            return response.json()
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


def fetch_osm_json_tiled(
    south: float,
    west: float,
    north: float,
    east: float,
    overpass_url: str = DEFAULT_OVERPASS_URL,
    tile_size_km: float = 2.5,
    progress: Progress | None = None,
) -> dict[str, Any]:
    tiles = _bbox_tiles(south, west, north, east, tile_size_km)
    elements: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    errors: list[str] = []

    for index, (ts, tw, tn, te) in enumerate(tiles, start=1):
        if progress:
            progress(f"Loading OpenStreetMap tile {index}/{len(tiles)}", (index - 1) / len(tiles))
        try:
            data = fetch_osm_json(ts, tw, tn, te, overpass_url, overpass_timeout_s=45, read_timeout_s=70)
        except OverpassFetchError as exc:
            if len(tiles) == 1:
                raise
            errors.append(f"tile {index}/{len(tiles)}: {exc}")
            time.sleep(0.5)
            continue
        for element in data.get("elements", []):
            key = (str(element.get("type", "")), str(element.get("id", "")))
            if key in seen:
                continue
            seen.add(key)
            elements.append(element)
        time.sleep(0.15)

    if progress:
        progress(f"Loaded {len(elements)} unique OpenStreetMap elements from {len(tiles)} tiles", 1.0)
    if not elements and errors:
        raise OverpassFetchError("; ".join(errors[:6]))
    return {
        "version": 0.6,
        "generator": "TopoTile Studio tiled Overpass fetch",
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
    if tags.get("waterway") in {"river", "stream", "canal", "ditch", "drain"}:
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
    return None


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


def _relation_member_lines(element: dict[str, Any], projection: LocalProjection) -> list[LineString]:
    lines: list[LineString] = []
    for member in element.get("members") or []:
        if member.get("type") != "way":
            continue
        raw_geom = member.get("geometry") or []
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


def _relation_member_lines_by_role(element: dict[str, Any], projection: LocalProjection) -> tuple[list[LineString], list[LineString], list[LineString]]:
    outer: list[LineString] = []
    inner: list[LineString] = []
    all_lines: list[LineString] = []
    for member in element.get("members") or []:
        if member.get("type") != "way":
            continue
        raw_geom = member.get("geometry") or []
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


def _polygons_from_relation(element: dict[str, Any], projection: LocalProjection, clip: Polygon) -> list[Polygon]:
    outer_lines, inner_lines, all_lines = _relation_member_lines_by_role(element, projection)
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

    for element in osm_json.get("elements", []):
        element_type = element.get("type")
        tags = {str(k): str(v) for k, v in (element.get("tags") or {}).items()}
        if element_type == "relation":
            layer = classify(tags, is_closed=True)
            if layer in {"water", "green", "building", "parking", "airport"}:
                for poly in _polygons_from_relation(element, projection, clip):
                    features.append(OSMFeature(layer=layer, geometry_m=poly, tags=tags, osm_id=f"relation/{element.get('id', 'unknown')}"))
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
            if layer in {"building", "water", "green", "parking", "airport"} and is_closed:
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
