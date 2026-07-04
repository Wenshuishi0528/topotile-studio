from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import time
from typing import Any, Iterable

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
from shapely.strtree import STRtree
from shapely.validation import make_valid
from shapely import wkb

from .cancel import CancelCheck, check_cancel
from .geo import LocalProjection
from .osm import OSMFeature

OVERTURE_BUILDING_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "osm" / "overture_buildings"
OVERTURE_MAX_BUILDINGS = 120_000
OVERTURE_MIN_AREA_M2 = 4.0
OVERTURE_OVERLAP_RATIO = 0.08


@dataclass(slots=True)
class OvertureBuildingResult:
    enabled: bool
    status: str
    source_rows: int = 0
    added: int = 0
    skipped_overlap: int = 0
    skipped_invalid: int = 0
    cache_hit: bool = False
    release: str = ""
    truncated: bool = False
    error: str = ""

    def to_summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "status": self.status,
            "source_rows": self.source_rows,
            "added": self.added,
            "skipped_overlap": self.skipped_overlap,
            "skipped_invalid": self.skipped_invalid,
            "cache_hit": self.cache_hit,
            "release": self.release,
            "truncated": self.truncated,
            "error": self.error,
        }


def _cache_key(south: float, west: float, north: float, east: float) -> str:
    payload = {
        "type": "overture_building",
        "schema": 1,
        "bbox": [round(west, 6), round(south, 6), round(east, 6), round(north, 6)],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _cache_path(south: float, west: float, north: float, east: float) -> Path:
    return OVERTURE_BUILDING_CACHE_DIR / f"{_cache_key(south, west, north, east)}.json"


def _load_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.stat().st_size <= 0:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("rows"), list) else None


def _save_cache(path: Path, payload: dict[str, Any]) -> None:
    OVERTURE_BUILDING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _safe_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return None


def _row_from_batch_dict(data: dict[str, list[Any]], index: int) -> dict[str, Any] | None:
    geometry = data.get("geometry", [None])[index]
    if geometry is None:
        return None
    try:
        geometry_hex = bytes(geometry).hex()
    except Exception:
        return None

    names = data.get("names", [None])[index]
    name = None
    if isinstance(names, dict):
        name = names.get("primary")

    row: dict[str, Any] = {
        "id": _safe_scalar(data.get("id", [""])[index]) or "",
        "geometry_wkb_hex": geometry_hex,
        "name": _safe_scalar(name),
    }
    for key in (
        "height",
        "min_height",
        "num_floors",
        "min_floor",
        "is_underground",
        "class",
        "subtype",
        "roof_shape",
        "roof_height",
    ):
        values = data.get(key)
        if values is not None:
            row[key] = _safe_scalar(values[index])
    return row


def _download_overture_rows(
    south: float,
    west: float,
    north: float,
    east: float,
    cancel_check: CancelCheck | None,
) -> tuple[list[dict[str, Any]], str, bool]:
    try:
        from overturemaps import record_batch_reader
        from overturemaps.core import get_latest_release
    except ImportError as exc:
        raise RuntimeError(
            "The optional overturemaps package is not installed. Run the launcher again or install requirements.txt."
        ) from exc

    check_cancel(cancel_check)
    release = str(get_latest_release() or "")
    check_cancel(cancel_check)
    reader = record_batch_reader(
        "building",
        bbox=(west, south, east, north),
        release=release or None,
        stac=True,
        connect_timeout=12,
        request_timeout=60,
    )
    check_cancel(cancel_check)
    if reader is None:
        return [], release, False

    rows: list[dict[str, Any]] = []
    truncated = False
    for batch in reader:
        check_cancel(cancel_check)
        if batch.num_rows <= 0:
            continue
        batch_dict = batch.to_pydict()
        for index in range(batch.num_rows):
            row = _row_from_batch_dict(batch_dict, index)
            if row is not None:
                rows.append(row)
            if len(rows) >= OVERTURE_MAX_BUILDINGS:
                truncated = True
                break
        if truncated:
            break
    return rows, release, truncated


def _overture_tags(row: dict[str, Any]) -> dict[str, str]:
    tags: dict[str, str] = {
        "building": "yes",
        "source": "Overture Maps Foundation",
    }
    if row.get("id"):
        tags["overture:id"] = str(row["id"])
    if row.get("name"):
        tags["name"] = str(row["name"])
    if row.get("height") is not None:
        tags["height"] = f"{float(row['height']):.2f}"
    if row.get("min_height") is not None:
        tags["min_height"] = f"{float(row['min_height']):.2f}"
    if row.get("num_floors") is not None:
        tags["building:levels"] = str(int(row["num_floors"]))
    if row.get("min_floor") is not None:
        tags["min_level"] = str(int(row["min_floor"]))
    if row.get("is_underground") is True:
        tags["location"] = "underground"
    if row.get("class"):
        tags["overture:class"] = str(row["class"])
    if row.get("subtype"):
        tags["overture:subtype"] = str(row["subtype"])
    if row.get("roof_shape"):
        tags["roof:shape"] = str(row["roof_shape"]).strip().lower()
    if row.get("roof_height") is not None:
        tags["roof:height"] = f"{float(row['roof_height']):.2f}"
    return tags


def _project_lonlat_geometry(geom: BaseGeometry, projection: LocalProjection) -> BaseGeometry:
    def project_xy(x: Any, y: Any, z: Any = None) -> Any:
        try:
            return projection.lonlat_to_local(float(x), float(y))
        except (TypeError, ValueError):
            xs: list[float] = []
            ys: list[float] = []
            for lon, lat in zip(x, y):
                px, py = projection.lonlat_to_local(float(lon), float(lat))
                xs.append(px)
                ys.append(py)
            return xs, ys

    return transform(project_xy, geom)


def _iter_polygons(geom: BaseGeometry) -> Iterable[Polygon]:
    if geom.is_empty:
        return
    if isinstance(geom, Polygon):
        yield geom
    elif isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            if not poly.is_empty:
                yield poly
    elif isinstance(geom, GeometryCollection):
        for part in geom.geoms:
            yield from _iter_polygons(part)


def _clean_polygon_geometry(geom: BaseGeometry, clip_m: BaseGeometry) -> BaseGeometry | None:
    if geom.is_empty:
        return None
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.is_empty:
        return None
    try:
        geom = geom.intersection(clip_m)
    except Exception:
        return None
    if geom.is_empty:
        return None
    if not geom.is_valid:
        geom = make_valid(geom)
    polys = [poly for poly in _iter_polygons(geom) if poly.area >= OVERTURE_MIN_AREA_M2]
    if not polys:
        return None
    if len(polys) == 1:
        return polys[0]
    try:
        return MultiPolygon(polys)
    except Exception:
        return None


def _existing_building_polygons(features: list[OSMFeature]) -> list[Polygon]:
    polys: list[Polygon] = []
    for feature in features:
        for poly in _iter_polygons(feature.geometry_m):
            if not poly.is_empty and poly.area >= OVERTURE_MIN_AREA_M2:
                polys.append(poly)
    return polys


def _overlaps_existing_building(geom: BaseGeometry, existing_polys: list[Polygon], existing_tree: STRtree | None) -> bool:
    if not existing_polys or existing_tree is None:
        return False
    for poly in _iter_polygons(geom):
        if poly.area <= 0:
            continue
        try:
            candidates = existing_tree.query(poly)
        except Exception:
            continue
        overlap_area = 0.0
        for raw_index in candidates:
            try:
                other = existing_polys[int(raw_index)]
            except (TypeError, ValueError, IndexError):
                continue
            if other.is_empty:
                continue
            try:
                overlap_area += float(poly.intersection(other).area)
            except Exception:
                continue
            if overlap_area / max(poly.area, 1e-6) >= OVERTURE_OVERLAP_RATIO:
                return True
        try:
            point = poly.representative_point()
            for raw_index in candidates:
                other = existing_polys[int(raw_index)]
                if other.covers(point):
                    return True
        except Exception:
            pass
    return False


def supplement_overture_buildings(
    south: float,
    west: float,
    north: float,
    east: float,
    projection: LocalProjection,
    existing_buildings: list[OSMFeature],
    clip_m: BaseGeometry,
    cancel_check: CancelCheck | None = None,
) -> tuple[list[OSMFeature], OvertureBuildingResult]:
    check_cancel(cancel_check)
    cache_path = _cache_path(south, west, north, east)
    cached = _load_cache(cache_path)
    cache_hit = cached is not None
    try:
        if cached is not None:
            rows = cached["rows"]
            release = str(cached.get("release") or "")
            truncated = bool(cached.get("truncated", False))
        else:
            rows, release, truncated = _download_overture_rows(south, west, north, east, cancel_check)
            _save_cache(cache_path, {
                "version": 1,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "release": release,
                "bbox": [south, west, north, east],
                "truncated": truncated,
                "rows": rows,
            })
    except Exception as exc:
        return [], OvertureBuildingResult(
            enabled=True,
            status="failed",
            cache_hit=cache_hit,
            error=str(exc)[:500],
        )

    existing_polys = _existing_building_polygons(existing_buildings)
    existing_tree = STRtree(existing_polys) if existing_polys else None
    features: list[OSMFeature] = []
    skipped_overlap = 0
    skipped_invalid = 0

    for row in rows:
        check_cancel(cancel_check)
        try:
            geom_wgs = wkb.loads(bytes.fromhex(str(row.get("geometry_wkb_hex", ""))))
            geom_m = _project_lonlat_geometry(geom_wgs, projection)
            geom_m = _clean_polygon_geometry(geom_m, clip_m)
        except Exception:
            geom_m = None
        if geom_m is None or geom_m.is_empty:
            skipped_invalid += 1
            continue
        if _overlaps_existing_building(geom_m, existing_polys, existing_tree):
            skipped_overlap += 1
            continue
        tags = _overture_tags(row)
        osm_id = f"overture/{tags.get('overture:id', len(features) + 1)}"
        features.append(OSMFeature(layer="building", geometry_m=geom_m, tags=tags, osm_id=osm_id))

    status = "complete"
    if truncated:
        status = "truncated"
    elif not rows:
        status = "empty"
    return features, OvertureBuildingResult(
        enabled=True,
        status=status,
        source_rows=len(rows),
        added=len(features),
        skipped_overlap=skipped_overlap,
        skipped_invalid=skipped_invalid,
        cache_hit=cache_hit,
        release=release,
        truncated=truncated,
    )
