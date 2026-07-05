from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import re
from typing import Any

import numpy as np
from shapely.ops import unary_union
from shapely.validation import make_valid

from .dem import TerrainGrid
from .geo import ModelScaler
from .mesh_ops import COLORS, iter_polygons, transform_polygon_to_mm
from .mesh_types import MeshPart
from .osm import OSMFeature
from .params import ModelParams


@dataclass(slots=True)
class LandmarkReplacementResult:
    building_features: list[OSMFeature]
    surface_building_features: list[OSMFeature]
    part: MeshPart | None
    summary: dict[str, Any]


def normalize_osm_id(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("：", ":").replace("\\", "/")
    typed = re.search(r"\b(way|relation|node)\D+(\d+)\b", text)
    if typed:
        return f"{typed.group(1)}/{typed.group(2)}"
    compact = text.replace(" ", "")
    if re.fullmatch(r"(way|relation|node)/\d+", compact):
        return compact
    digits = re.search(r"\d+", compact)
    return digits.group(0) if digits else compact


def _osm_id_matches(feature_id: str, query: str) -> bool:
    feature = normalize_osm_id(feature_id)
    target = normalize_osm_id(query)
    if not feature or not target:
        return False
    if "/" in target:
        return feature == target
    return feature.split("/")[-1] == target


def find_landmark_target(features: list[OSMFeature], target_osm_id: str) -> OSMFeature | None:
    for feature in features:
        if _osm_id_matches(feature.osm_id, target_osm_id):
            return feature
    return None


def _valid_geometry(feature: OSMFeature):
    try:
        geom = make_valid(feature.geometry_m)
    except Exception:
        return None
    if geom.is_empty or geom.area <= 0:
        return None
    return geom


def _overlaps_target(feature: OSMFeature, target: OSMFeature, threshold: float = 0.45) -> bool:
    if _osm_id_matches(feature.osm_id, target.osm_id):
        return True
    geom = _valid_geometry(feature)
    target_geom = _valid_geometry(target)
    if geom is None or target_geom is None:
        return False
    try:
        intersection_area = float(geom.intersection(target_geom).area)
    except Exception:
        return False
    if intersection_area <= 0:
        return False
    smaller = min(float(geom.area), float(target_geom.area))
    return smaller > 0 and intersection_area / smaller >= threshold


def filter_replaced_buildings(
    buildings: list[OSMFeature],
    target: OSMFeature,
    replace_original: bool,
) -> tuple[list[OSMFeature], list[OSMFeature]]:
    if not replace_original:
        return list(buildings), []
    kept: list[OSMFeature] = []
    removed: list[OSMFeature] = []
    for feature in buildings:
        if _overlaps_target(feature, target):
            removed.append(feature)
        else:
            kept.append(feature)
    return kept, removed


def _load_mesh(path: str | Path):
    try:
        import trimesh
    except Exception as exc:  # pragma: no cover
        raise ValueError("trimesh is required for landmark model import.") from exc

    model_path = Path(path)
    try:
        loaded = trimesh.load(model_path, force="scene", process=False)
    except Exception as exc:
        raise ValueError(f"Could not load landmark model '{model_path.name}': {exc}") from exc

    if isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        try:
            mesh = loaded.to_geometry() if hasattr(loaded, "to_geometry") else loaded.dump(concatenate=True)
        except Exception as exc:
            raise ValueError(f"Could not combine landmark model geometry: {exc}") from exc
        if isinstance(mesh, list):
            meshes = [item for item in mesh if isinstance(item, trimesh.Trimesh) and len(item.faces) > 0]
            if not meshes:
                raise ValueError("Landmark model contains no mesh geometry.")
            mesh = trimesh.util.concatenate(meshes)

    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError("Landmark model contains no usable mesh geometry.")
    return mesh


def _target_footprint_mm(target: OSMFeature, scaler: ModelScaler, params: ModelParams):
    tol_m = scaler.length_mm_to_m(params.simplify_tolerance_mm)
    polygons = []
    for poly_m in iter_polygons(target.geometry_m):
        poly = transform_polygon_to_mm(poly_m, scaler, tol_m)
        if poly is not None and not poly.is_empty:
            polygons.append(poly)
    if not polygons:
        raise ValueError("Target OSM building has no printable footprint after clipping.")
    try:
        footprint = unary_union(polygons)
    except Exception as exc:
        raise ValueError("Could not build target landmark footprint.") from exc
    if footprint.is_empty:
        raise ValueError("Target OSM building has an empty footprint.")
    return footprint


def build_landmark_mesh(
    target: OSMFeature,
    model_path: str | Path,
    scaler: ModelScaler,
    terrain: TerrainGrid,
    params: ModelParams,
) -> tuple[MeshPart, dict[str, Any]]:
    mesh = _load_mesh(model_path)
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)

    finite = np.all(np.isfinite(vertices), axis=1)
    if not finite.all():
        remap = np.full(len(vertices), -1, dtype=np.int64)
        remap[finite] = np.arange(finite.sum())
        valid_faces = np.all(finite[faces], axis=1)
        vertices = vertices[finite]
        faces = remap[faces[valid_faces]]
    if vertices.size == 0 or faces.size == 0:
        raise ValueError("Landmark model contains only invalid geometry.")

    source_min = vertices.min(axis=0)
    source_max = vertices.max(axis=0)
    source_size = source_max - source_min
    source_xy_max = float(max(source_size[0], source_size[1]))
    if source_xy_max <= 0:
        raise ValueError("Landmark model has zero XY size.")

    footprint = _target_footprint_mm(target, scaler, params)
    minx, miny, maxx, maxy = footprint.bounds
    target_width = float(maxx - minx)
    target_height = float(maxy - miny)
    target_xy_max = max(target_width, target_height)
    if target_xy_max <= 0:
        raise ValueError("Target OSM building has zero footprint size.")
    center = footprint.centroid
    center_x = float(center.x)
    center_y = float(center.y)

    fit_scale = target_xy_max / source_xy_max if params.landmark_fit_to_footprint else 1.0
    total_scale = fit_scale * params.landmark_scale
    if total_scale <= 0 or not math.isfinite(total_scale):
        raise ValueError("Landmark model scale is invalid.")

    transformed = vertices.copy()
    source_center_x = float((source_min[0] + source_max[0]) / 2.0)
    source_center_y = float((source_min[1] + source_max[1]) / 2.0)
    transformed[:, 0] -= source_center_x
    transformed[:, 1] -= source_center_y
    transformed[:, 2] -= float(source_min[2])
    transformed *= total_scale

    angle = math.radians(params.landmark_rotation_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    x = transformed[:, 0].copy()
    y = transformed[:, 1].copy()
    transformed[:, 0] = x * cos_a - y * sin_a + center_x
    transformed[:, 1] = x * sin_a + y * cos_a + center_y
    transformed[:, 2] += terrain.sample_z(center_x, center_y) + params.landmark_z_offset_mm

    part = MeshPart("landmark", transformed, faces, COLORS["landmark"]).cleaned()
    if part.is_empty():
        raise ValueError("Landmark model became empty after placement.")

    summary = {
        "source_file": Path(model_path).name,
        "matched_osm_id": target.osm_id,
        "vertices": int(len(part.vertices)),
        "triangles": int(len(part.faces)),
        "source_size": [float(value) for value in source_size],
        "target_footprint_mm": {
            "width": target_width,
            "height": target_height,
        },
        "fit_scale": float(fit_scale),
        "user_scale": float(params.landmark_scale),
        "total_scale": float(total_scale),
        "rotation_deg": float(params.landmark_rotation_deg),
        "z_offset_mm": float(params.landmark_z_offset_mm),
        "fit_to_footprint": bool(params.landmark_fit_to_footprint),
    }
    return part, summary


def apply_landmark_replacement(
    buildings: list[OSMFeature],
    osm_buildings: list[OSMFeature],
    landmark_model_path: str | Path | None,
    scaler: ModelScaler,
    terrain: TerrainGrid,
    params: ModelParams,
) -> LandmarkReplacementResult:
    disabled_summary = {
        "enabled": False,
        "status": "disabled",
        "target_osm_id": "",
        "removed_buildings": 0,
    }
    if not params.include_landmark_replacement:
        return LandmarkReplacementResult(list(buildings), list(buildings), None, disabled_summary)
    if not landmark_model_path:
        raise ValueError("Landmark replacement requires an uploaded GLB/GLTF/OBJ/STL/DAE model file.")

    target = find_landmark_target(osm_buildings, params.landmark_osm_id)
    if target is None:
        raise ValueError(
            f"Landmark target OSM ID '{params.landmark_osm_id}' was not found among building features."
        )

    filtered, removed = filter_replaced_buildings(buildings, target, params.landmark_replace_original)
    part, mesh_summary = build_landmark_mesh(target, landmark_model_path, scaler, terrain, params)
    surface_buildings = list(buildings) if params.landmark_replace_original else list(filtered)
    summary = {
        "enabled": True,
        "status": "complete",
        "target_osm_id": params.landmark_osm_id,
        "matched_osm_id": target.osm_id,
        "replace_original": bool(params.landmark_replace_original),
        "removed_buildings": len(removed),
        **mesh_summary,
    }
    return LandmarkReplacementResult(filtered, surface_buildings, part, summary)
