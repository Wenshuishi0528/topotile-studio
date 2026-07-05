from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

from shapely.geometry import LineString, MultiLineString, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
from shapely.validation import make_valid

from .geo import LocalProjection
from .osm import OSMFeature, classify

SUPPORTED_VECTOR_LAYERS = {
    "building",
    "road",
    "water",
    "green",
    "parking",
    "airport",
    "area_infill",
    "rail_line",
    "rail_station",
    "subway_line",
    "subway_station",
}

DIRECT_LAYER_ALIASES = {
    "building": "building",
    "buildings": "building",
    "buildingpart": "building",
    "house": "building",
    "houses": "building",
    "房屋": "building",
    "建筑": "building",
    "建筑物": "building",
    "road": "road",
    "roads": "road",
    "street": "road",
    "highway": "road",
    "道路": "road",
    "公路": "road",
    "路网": "road",
    "water": "water",
    "waters": "water",
    "river": "water",
    "lake": "water",
    "pond": "water",
    "canal": "water",
    "水": "water",
    "水体": "water",
    "湖泊": "water",
    "河流": "water",
    "green": "green",
    "greenspace": "green",
    "park": "green",
    "garden": "green",
    "vegetation": "green",
    "绿地": "green",
    "公园": "green",
    "植被": "green",
    "parking": "parking",
    "parkinglot": "parking",
    "停车": "parking",
    "停车场": "parking",
    "airport": "airport",
    "runway": "airport",
    "taxiway": "airport",
    "apron": "airport",
    "机场": "airport",
    "跑道": "airport",
    "滑行道": "airport",
    "area": "area_infill",
    "infill": "area_infill",
    "areainfill": "area_infill",
    "landuse": "area_infill",
    "parcel": "area_infill",
    "polygon": "area_infill",
    "补面": "area_infill",
    "区域": "area_infill",
    "用地": "area_infill",
    "rail": "rail_line",
    "railway": "rail_line",
    "train": "rail_line",
    "铁路": "rail_line",
    "火车": "rail_line",
    "subway": "subway_line",
    "metro": "subway_line",
    "地铁": "subway_line",
    "railstation": "rail_station",
    "trainstation": "rail_station",
    "火车站": "rail_station",
    "铁路站": "rail_station",
    "subwaystation": "subway_station",
    "metrostation": "subway_station",
    "地铁站": "subway_station",
}

LAYER_PROPERTY_KEYS = (
    "topotile_layer",
    "topotile:layer",
    "layer",
    "class",
    "type",
    "kind",
    "category",
    "类别",
    "类型",
    "图层",
    "要素类型",
)


def load_vector_features(
    path: str | Path,
    projection: LocalProjection,
    coordinate_system: str = "wgs84",
) -> tuple[list[OSMFeature], dict[str, Any]]:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return parse_geojson_features(data, projection, coordinate_system=coordinate_system)


def parse_geojson_features(
    data: dict[str, Any],
    projection: LocalProjection,
    coordinate_system: str = "wgs84",
) -> tuple[list[OSMFeature], dict[str, Any]]:
    raw_features = list(_iter_geojson_features(data))
    features: list[OSMFeature] = []
    skipped = 0
    counts: dict[str, int] = {layer: 0 for layer in SUPPORTED_VECTOR_LAYERS}
    for index, feature in enumerate(raw_features, start=1):
        props = {str(k): v for k, v in (feature.get("properties") or {}).items()}
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            skipped += 1
            continue
        layer = _layer_from_properties(props, geometry.get("type"))
        if layer not in SUPPORTED_VECTOR_LAYERS:
            skipped += 1
            continue
        try:
            geom = shape(geometry)
        except Exception:
            skipped += 1
            continue
        geom = _geojson_geom_to_local(geom, projection, coordinate_system)
        geom = _safe_geom_for_layer(geom, layer)
        if geom is None:
            skipped += 1
            continue
        tags = _tags_for_layer(layer, props, geom)
        osm_id = _feature_id(feature, index)
        features.append(OSMFeature(layer=layer, geometry_m=geom, tags=tags, osm_id=osm_id))
        counts[layer] += 1

    counts = {layer: count for layer, count in counts.items() if count}
    summary = {
        "source": "local_vector",
        "format": "geojson",
        "coordinate_system": coordinate_system,
        "input_features": len(raw_features),
        "features": len(features),
        "skipped": skipped,
        "layers": counts,
    }
    return features, summary


def _iter_geojson_features(data: dict[str, Any]) -> Iterable[dict[str, Any]]:
    if data.get("type") == "FeatureCollection":
        for feature in data.get("features") or []:
            if isinstance(feature, dict):
                yield feature
    elif data.get("type") == "Feature":
        yield data
    elif "type" in data and "coordinates" in data:
        yield {"type": "Feature", "properties": {}, "geometry": data}


def _feature_id(feature: dict[str, Any], index: int) -> str:
    raw_id = feature.get("id")
    if raw_id is None:
        raw_id = (feature.get("properties") or {}).get("id")
    return f"local/{raw_id}" if raw_id not in (None, "") else f"local/{index}"


def _normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def _property(props: dict[str, Any], *keys: str) -> str:
    lower = {str(k).lower(): v for k, v in props.items()}
    for key in keys:
        if key in props and props[key] not in (None, ""):
            return str(props[key]).strip()
        value = lower.get(key.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _layer_from_properties(props: dict[str, Any], geom_type: object) -> str | None:
    for key in LAYER_PROPERTY_KEYS:
        value = _property(props, key)
        normalized = _normalize_text(value)
        if normalized in DIRECT_LAYER_ALIASES:
            return DIRECT_LAYER_ALIASES[normalized]
        if normalized in SUPPORTED_VECTOR_LAYERS:
            return normalized

    string_tags = {str(k): str(v) for k, v in props.items() if v not in (None, "")}
    is_closed = str(geom_type or "").lower() in {"polygon", "multipolygon"}
    layer = classify(string_tags, is_closed=is_closed)
    if layer in SUPPORTED_VECTOR_LAYERS:
        return layer
    return None


def _tags_for_layer(layer: str, props: dict[str, Any], geom: BaseGeometry) -> dict[str, str]:
    tags = {str(k): str(v) for k, v in props.items() if v not in (None, "")}
    if layer == "building":
        tags.setdefault("building", "yes")
    elif layer == "road":
        tags["highway"] = _road_level(props)
    elif layer == "water":
        if _has_linear_geometry(geom):
            tags.setdefault("waterway", _property(props, "waterway") or "river")
        else:
            tags.setdefault("natural", "water")
    elif layer == "green":
        tags.setdefault("leisure", "park")
    elif layer == "parking":
        tags.setdefault("amenity", "parking")
        tags.setdefault("parking", "surface")
    elif layer == "airport":
        tags.setdefault("aeroway", _aeroway_type(props, geom))
    elif layer == "area_infill":
        tags.setdefault("landuse", _property(props, "landuse") or "residential")
    elif layer == "rail_line":
        tags.setdefault("railway", "rail")
    elif layer == "subway_line":
        tags.setdefault("railway", "subway")
    elif layer == "rail_station":
        tags.setdefault("railway", "station")
    elif layer == "subway_station":
        tags.setdefault("railway", "subway_entrance")
        tags.setdefault("station", "subway")
    return tags


def _road_level(props: dict[str, Any]) -> str:
    for key in ("highway", "road_level", "road_type", "level", "class", "type", "类别", "类型"):
        value = _normalize_text(_property(props, key))
        if value in {
            "motorway",
            "trunk",
            "primary",
            "secondary",
            "tertiary",
            "unclassified",
            "residential",
            "livingstreet",
            "service",
            "pedestrian",
            "track",
            "cycleway",
            "footway",
            "path",
            "steps",
        }:
            return "living_street" if value == "livingstreet" else value
        if value in {"高速", "高速公路"}:
            return "motorway"
        if value in {"主干路", "主路"}:
            return "primary"
        if value in {"次干路", "次路"}:
            return "secondary"
        if value in {"支路", "街道", "道路", "公路"}:
            return "residential"
        if value in {"步道", "人行道"}:
            return "footway"
    return "residential"


def _aeroway_type(props: dict[str, Any], geom: BaseGeometry) -> str:
    value = _normalize_text(_property(props, "aeroway", "class", "type", "类别", "类型"))
    if value in {"runway", "跑道"}:
        return "runway"
    if value in {"taxiway", "滑行道"}:
        return "taxiway"
    if value in {"apron", "停机坪"}:
        return "apron"
    return "taxiway" if _has_linear_geometry(geom) else "apron"


def _has_linear_geometry(geom: BaseGeometry) -> bool:
    return isinstance(geom, (LineString, MultiLineString))


def _safe_geom_for_layer(geom: BaseGeometry, layer: str) -> BaseGeometry | None:
    if geom.is_empty:
        return None
    try:
        if not geom.is_valid:
            geom = make_valid(geom)
    except Exception:
        return None
    if geom.is_empty:
        return None
    if layer in {"rail_station", "subway_station"}:
        return geom
    if layer in {"road", "rail_line", "subway_line"}:
        if isinstance(geom, Point):
            return None
        return geom
    if isinstance(geom, (Polygon,)):
        return geom if geom.area > 0 else None
    if geom.geom_type == "MultiPolygon":
        return geom if geom.area > 0 else None
    if layer in {"water", "airport"} and _has_linear_geometry(geom):
        return geom
    return None


def _geojson_geom_to_local(
    geom: BaseGeometry,
    projection: LocalProjection,
    coordinate_system: str,
) -> BaseGeometry:
    def convert(lon: float, lat: float, z: float | None = None):
        wgs_lon, wgs_lat = coordinate_to_wgs84(float(lon), float(lat), coordinate_system)
        x, y = projection.lonlat_to_local(wgs_lon, wgs_lat)
        return (x, y) if z is None else (x, y, z)

    return transform(convert, geom)


def coordinate_to_wgs84(lon: float, lat: float, coordinate_system: str) -> tuple[float, float]:
    system = str(coordinate_system or "wgs84").lower()
    if system == "gcj02":
        return gcj02_to_wgs84(lon, lat)
    if system == "bd09":
        return gcj02_to_wgs84(*bd09_to_gcj02(lon, lat))
    return lon, lat


def _out_of_china(lon: float, lat: float) -> bool:
    return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271


def _transform_lat(lon: float, lat: float) -> float:
    ret = -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat + 0.1 * lon * lat + 0.2 * math.sqrt(abs(lon))
    ret += (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(lon: float, lat: float) -> float:
    ret = 300.0 + lon + 2.0 * lat + 0.1 * lon * lon + 0.1 * lon * lat + 0.1 * math.sqrt(abs(lon))
    ret += (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lon * math.pi) + 40.0 * math.sin(lon / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lon / 12.0 * math.pi) + 300.0 * math.sin(lon / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def _gcj_delta(lon: float, lat: float) -> tuple[float, float]:
    a = 6378245.0
    ee = 0.00669342162296594323
    d_lat = _transform_lat(lon - 105.0, lat - 35.0)
    d_lon = _transform_lon(lon - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - ee * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((a * (1 - ee)) / (magic * sqrt_magic) * math.pi)
    d_lon = (d_lon * 180.0) / (a / sqrt_magic * math.cos(rad_lat) * math.pi)
    return d_lon, d_lat


def gcj02_to_wgs84(lon: float, lat: float) -> tuple[float, float]:
    if _out_of_china(lon, lat):
        return lon, lat
    d_lon, d_lat = _gcj_delta(lon, lat)
    return lon - d_lon, lat - d_lat


def bd09_to_gcj02(lon: float, lat: float) -> tuple[float, float]:
    x = lon - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * math.pi * 3000.0 / 180.0)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * math.pi * 3000.0 / 180.0)
    return z * math.cos(theta), z * math.sin(theta)
