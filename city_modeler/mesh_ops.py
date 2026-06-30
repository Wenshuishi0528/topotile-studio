from __future__ import annotations

from collections.abc import Iterable
import math
import re
import numpy as np

from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from shapely.geometry.base import BaseGeometry
from shapely import constrained_delaunay_triangles
from shapely.ops import triangulate, unary_union
from shapely.prepared import prep
from shapely.validation import make_valid

from .dem import TerrainGrid
from .geo import ModelScaler
from .mesh_types import MeshPart, merge_parts
from .osm import OSMFeature
from .params import ModelParams

COLORS = {
    "terrain": (198, 188, 160, 255),
    "buildings": (230, 230, 225, 255),
    "roads": (120, 120, 120, 255),
    "water": (60, 140, 220, 255),
    "green": (80, 160, 90, 255),
    "parking": (168, 168, 156, 255),
    "airport": (168, 168, 156, 255),
}


def _terrain_cut_mask(
    grid: TerrainGrid,
    cutouts_mm: Iterable[Polygon] | None,
    footprint_mm: BaseGeometry | None = None,
) -> np.ndarray | None:
    cutouts = [poly for poly in (cutouts_mm or []) if not poly.is_empty]
    footprint = footprint_mm if footprint_mm is not None and not footprint_mm.is_empty else None
    if not cutouts and footprint is None:
        return None
    cutout_union = None
    if cutouts:
        try:
            cutout_union = unary_union(cutouts)
        except Exception:
            cutout_union = None
        if cutout_union is not None and cutout_union.is_empty:
            cutout_union = None

    ny, nx = grid.z_mm.shape
    mask = np.zeros((ny - 1, nx - 1), dtype=bool)
    for j in range(ny - 1):
        for i in range(nx - 1):
            x0 = float(grid.x_mm[j, i])
            x1 = float(grid.x_mm[j, i + 1])
            y0 = float(grid.y_mm[j, i])
            y1 = float(grid.y_mm[j + 1, i])
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            try:
                cell = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
            except Exception:
                continue
            if footprint is not None:
                if not footprint.covers(Point(cx, cy)):
                    try:
                        inside_ratio = footprint.intersection(cell).area / cell.area if cell.area > 0 else 0.0
                    except Exception:
                        inside_ratio = 0.0
                    if inside_ratio < 0.35:
                        mask[j, i] = True
                        continue
            if cutout_union is not None:
                if cutout_union.covers(Point(cx, cy)):
                    mask[j, i] = True
                    continue
                try:
                    mask[j, i] = cell.area > 0 and cutout_union.intersection(cell).area / cell.area >= 0.35
                except Exception:
                    continue
    return mask


def terrain_to_mesh(
    grid: TerrainGrid,
    name: str = "terrain",
    cutouts_mm: Iterable[Polygon] | None = None,
    footprint_mm: BaseGeometry | None = None,
) -> MeshPart:
    ny, nx = grid.z_mm.shape
    top_vertices = np.column_stack([grid.x_mm.ravel(), grid.y_mm.ravel(), grid.z_mm.ravel()])
    bottom_vertices = np.column_stack([grid.x_mm.ravel(), grid.y_mm.ravel(), np.zeros(nx * ny)])
    vertices = np.vstack([top_vertices, bottom_vertices])
    faces: list[tuple[int, int, int]] = []
    cut_mask = _terrain_cut_mask(grid, cutouts_mm, footprint_mm)

    def tid(i: int, j: int) -> int:
        return j * nx + i

    def bid(i: int, j: int) -> int:
        return nx * ny + j * nx + i

    def is_cut(i: int, j: int) -> bool:
        return bool(cut_mask is not None and cut_mask[j, i])

    def cell_exists(i: int, j: int) -> bool:
        return 0 <= i < nx - 1 and 0 <= j < ny - 1 and not is_cut(i, j)

    for j in range(ny - 1):
        for i in range(nx - 1):
            if is_cut(i, j):
                continue
            a = tid(i, j)
            b = tid(i + 1, j)
            c = tid(i + 1, j + 1)
            d = tid(i, j + 1)
            faces.append((a, b, c))
            faces.append((a, c, d))
            ab = bid(i, j)
            bb = bid(i + 1, j)
            cb = bid(i + 1, j + 1)
            db = bid(i, j + 1)
            faces.append((ab, cb, bb))
            faces.append((ab, db, cb))

    for j in range(ny - 1):
        for i in range(nx - 1):
            if is_cut(i, j):
                continue
            if not cell_exists(i, j - 1):
                a = tid(i, j); b = tid(i + 1, j); ab = bid(i, j); bb = bid(i + 1, j)
                faces.append((a, ab, bb)); faces.append((a, bb, b))
            if not cell_exists(i, j + 1):
                d = tid(i, j + 1); c = tid(i + 1, j + 1); db = bid(i, j + 1); cb = bid(i + 1, j + 1)
                faces.append((d, c, cb)); faces.append((d, cb, db))
            if not cell_exists(i - 1, j):
                a = tid(i, j); d = tid(i, j + 1); ab = bid(i, j); db = bid(i, j + 1)
                faces.append((a, d, db)); faces.append((a, db, ab))
            if not cell_exists(i + 1, j):
                b = tid(i + 1, j); c = tid(i + 1, j + 1); bb = bid(i + 1, j); cb = bid(i + 1, j + 1)
                faces.append((b, bb, cb)); faces.append((b, cb, c))

    return MeshPart(name, vertices, np.asarray(faces, dtype=np.int64), COLORS["terrain"]).cleaned()


def _signed_area(coords: list[tuple[float, float]]) -> float:
    area = 0.0
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        area += x0 * y1 - x1 * y0
    return area / 2.0


def _add_triangle(vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]], coords: list[tuple[float, float]], z: float, up: bool) -> None:
    if len(coords) < 3:
        return
    tri = coords[:3]
    area = _signed_area(tri + [tri[0]])
    idx = len(vertices)
    vertices.extend([(tri[0][0], tri[0][1], z), (tri[1][0], tri[1][1], z), (tri[2][0], tri[2][1], z)])
    if up:
        faces.append((idx, idx + 1, idx + 2) if area >= 0 else (idx, idx + 2, idx + 1))
    else:
        faces.append((idx, idx + 2, idx + 1) if area >= 0 else (idx, idx + 1, idx + 2))


def _add_ring_sides(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    ring: Iterable[tuple[float, float]],
    z0: float,
    z1: float,
    reverse: bool = False,
) -> None:
    coords = list(ring)
    if len(coords) < 4:
        return
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    for p0, p1 in zip(coords, coords[1:]):
        if p0 == p1:
            continue
        idx = len(vertices)
        vertices.extend([(p0[0], p0[1], z0), (p1[0], p1[1], z0), (p1[0], p1[1], z1), (p0[0], p0[1], z1)])
        if not reverse:
            faces.append((idx, idx + 1, idx + 2))
            faces.append((idx, idx + 2, idx + 3))
        else:
            faces.append((idx, idx + 2, idx + 1))
            faces.append((idx, idx + 3, idx + 2))


def _triangulate_polygon(poly: Polygon) -> list[Polygon]:
    try:
        constrained = constrained_delaunay_triangles(poly)
        triangles = list(iter_polygons(constrained))
    except Exception:
        triangles = []
    if not triangles:
        try:
            triangles = triangulate(poly)
        except Exception:
            triangles = []
    return [
        tri
        for tri in triangles
        if not tri.is_empty and tri.area > 1e-9 and poly.covers(tri.representative_point())
    ]


def _clean_polygon(poly: Polygon, min_area: float = 1e-6) -> Polygon | None:
    if poly.is_empty:
        return None
    if not poly.is_valid:
        poly = make_valid(poly)
    if isinstance(poly, MultiPolygon):  # type: ignore[unreachable]
        poly = max(poly.geoms, key=lambda g: g.area)
    if not isinstance(poly, Polygon) or poly.area <= min_area:
        return None
    return poly


def extrude_polygon(poly: Polygon, z0: float, z1: float, name: str, color: tuple[int, int, int, int]) -> MeshPart:
    poly = _clean_polygon(poly)  # type: ignore[assignment]
    if poly is None or z1 <= z0:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []

    for tri in _triangulate_polygon(poly):
        coords = [(float(x), float(y)) for x, y in list(tri.exterior.coords)[:3]]
        _add_triangle(vertices, faces, coords, z1, up=True)
        _add_triangle(vertices, faces, coords, z0, up=False)

    _add_ring_sides(vertices, faces, [(float(x), float(y)) for x, y in poly.exterior.coords], z0, z1, reverse=False)
    for interior in poly.interiors:
        _add_ring_sides(vertices, faces, [(float(x), float(y)) for x, y in interior.coords], z0, z1, reverse=True)

    if not faces:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    return MeshPart(name, np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64), color).cleaned()


def _terrain_has_relief(terrain: TerrainGrid) -> bool:
    return bool(float(np.nanmax(terrain.z_mm) - np.nanmin(terrain.z_mm)) > 1e-6)


def _terrain_spacing_mm(terrain: TerrainGrid) -> float:
    candidates: list[float] = []
    xs = terrain.x_mm[0, :]
    ys = terrain.y_mm[:, 0]
    if len(xs) > 1:
        dx = np.diff(xs)
        dx = dx[np.isfinite(dx) & (dx > 0)]
        if dx.size:
            candidates.append(float(np.median(dx)))
    if len(ys) > 1:
        dy = np.diff(ys)
        dy = dy[np.isfinite(dy) & (dy > 0)]
        if dy.size:
            candidates.append(float(np.median(dy)))
    return max(0.5, min(candidates) if candidates else 2.0)


def _dedupe_xy(points: Iterable[tuple[float, float]], precision: float = 1e-5) -> list[tuple[float, float]]:
    seen: set[tuple[int, int]] = set()
    out: list[tuple[float, float]] = []
    for x, y in points:
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        key = (int(round(x / precision)), int(round(y / precision)))
        if key in seen:
            continue
        seen.add(key)
        out.append((float(x), float(y)))
    return out


def _densify_ring_xy(ring: Iterable[tuple[float, float]], max_step_mm: float) -> list[tuple[float, float]]:
    coords = [(float(x), float(y)) for x, y in ring]
    if len(coords) < 2:
        return coords
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    out: list[tuple[float, float]] = []
    for p0, p1 in zip(coords, coords[1:]):
        if not out:
            out.append(p0)
        length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        steps = max(1, int(math.ceil(length / max(max_step_mm, 0.5))))
        for step in range(1, steps + 1):
            t = step / steps
            out.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t))
    return out


def _terrain_points_inside_polygon(poly: Polygon, terrain: TerrainGrid, max_points: int = 5000) -> list[tuple[float, float]]:
    minx, miny, maxx, maxy = poly.bounds
    xs = terrain.x_mm[0, :]
    ys = terrain.y_mm[:, 0]
    ix0 = max(0, int(np.searchsorted(xs, minx, side="left")) - 1)
    ix1 = min(len(xs), int(np.searchsorted(xs, maxx, side="right")) + 1)
    iy0 = max(0, int(np.searchsorted(ys, miny, side="left")) - 1)
    iy1 = min(len(ys), int(np.searchsorted(ys, maxy, side="right")) + 1)
    total = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    if total <= 0:
        return []
    stride = max(1, int(math.ceil(math.sqrt(total / max_points)))) if total > max_points else 1
    prepared = prep(poly)
    points: list[tuple[float, float]] = []
    for iy in range(iy0, iy1, stride):
        for ix in range(ix0, ix1, stride):
            x = float(xs[ix])
            y = float(ys[iy])
            point = Point(x, y)
            if prepared.contains(point) or poly.touches(point):
                points.append((x, y))
    return points


def _add_terrain_triangle(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    coords: list[tuple[float, float]],
    terrain: TerrainGrid,
    z_offset_mm: float,
    thickness_mm: float,
) -> None:
    if len(coords) < 3:
        return
    tri = coords[:3]
    area = _signed_area(tri + [tri[0]])
    if abs(area) <= 1e-12:
        return
    bottom = [terrain.sample_z(x, y) + z_offset_mm for x, y in tri]
    top = [z + thickness_mm for z in bottom]
    idx = len(vertices)
    vertices.extend([(x, y, z) for (x, y), z in zip(tri, top)])
    vertices.extend([(x, y, z) for (x, y), z in zip(tri, bottom)])
    if area >= 0:
        faces.append((idx, idx + 1, idx + 2))
        faces.append((idx + 3, idx + 5, idx + 4))
    else:
        faces.append((idx, idx + 2, idx + 1))
        faces.append((idx + 3, idx + 4, idx + 5))


def _add_terrain_ring_sides(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    ring: Iterable[tuple[float, float]],
    terrain: TerrainGrid,
    z_offset_mm: float,
    thickness_mm: float,
    reverse: bool = False,
) -> None:
    coords = list(ring)
    if len(coords) < 4:
        return
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    for p0, p1 in zip(coords, coords[1:]):
        if p0 == p1:
            continue
        b0 = terrain.sample_z(p0[0], p0[1]) + z_offset_mm
        b1 = terrain.sample_z(p1[0], p1[1]) + z_offset_mm
        idx = len(vertices)
        vertices.extend([
            (p0[0], p0[1], b0),
            (p1[0], p1[1], b1),
            (p1[0], p1[1], b1 + thickness_mm),
            (p0[0], p0[1], b0 + thickness_mm),
        ])
        if not reverse:
            faces.append((idx, idx + 1, idx + 2))
            faces.append((idx, idx + 2, idx + 3))
        else:
            faces.append((idx, idx + 2, idx + 1))
            faces.append((idx, idx + 3, idx + 2))


def extrude_polygon_on_terrain(
    poly: Polygon,
    terrain: TerrainGrid,
    z_offset_mm: float,
    thickness_mm: float,
    name: str,
    color: tuple[int, int, int, int],
) -> MeshPart:
    poly = _clean_polygon(poly)  # type: ignore[assignment]
    if poly is None or thickness_mm <= 0:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    if not _terrain_has_relief(terrain):
        point = poly.representative_point()
        z0 = terrain.sample_z(point.x, point.y) + z_offset_mm
        return extrude_polygon(poly, z0, z0 + thickness_mm, name, color)

    spacing = _terrain_spacing_mm(terrain)
    max_step = max(0.5, spacing)
    exterior = _densify_ring_xy(poly.exterior.coords, max_step)
    holes = [_densify_ring_xy(ring.coords, max_step) for ring in poly.interiors]
    point_candidates: list[tuple[float, float]] = []
    point_candidates.extend(exterior[:-1])
    for hole in holes:
        point_candidates.extend(hole[:-1])
    point_candidates.extend(_terrain_points_inside_polygon(poly, terrain))
    points = _dedupe_xy(point_candidates)

    if len(points) < 3:
        point = poly.representative_point()
        z0 = terrain.sample_z(point.x, point.y) + z_offset_mm
        return extrude_polygon(poly, z0, z0 + thickness_mm, name, color)

    try:
        candidates = triangulate(MultiPoint(points))
    except Exception:
        candidates = []
    if not candidates:
        candidates = _triangulate_polygon(poly)

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for candidate in candidates:
        if candidate.is_empty or candidate.area <= 1e-9:
            continue
        try:
            clipped = candidate.intersection(poly)
        except Exception:
            continue
        for piece in iter_polygons(clipped):
            for tri in _triangulate_polygon(piece):
                coords = [(float(x), float(y)) for x, y in list(tri.exterior.coords)[:3]]
                _add_terrain_triangle(vertices, faces, coords, terrain, z_offset_mm, thickness_mm)

    _add_terrain_ring_sides(vertices, faces, exterior, terrain, z_offset_mm, thickness_mm, reverse=False)
    for hole in holes:
        _add_terrain_ring_sides(vertices, faces, hole, terrain, z_offset_mm, thickness_mm, reverse=True)

    if not faces:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    return MeshPart(name, np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64), color).cleaned()


def iter_polygons(geom: BaseGeometry) -> Iterable[Polygon]:
    if geom.is_empty:
        return
    if isinstance(geom, Polygon):
        yield geom
    elif isinstance(geom, MultiPolygon):
        for g in geom.geoms:
            yield g
    elif isinstance(geom, GeometryCollection):
        for g in geom.geoms:
            yield from iter_polygons(g)


def iter_lines(geom: BaseGeometry) -> Iterable[LineString]:
    if geom.is_empty:
        return
    if isinstance(geom, LineString):
        yield geom
    elif isinstance(geom, MultiLineString):
        for g in geom.geoms:
            yield g
    elif isinstance(geom, GeometryCollection):
        for g in geom.geoms:
            yield from iter_lines(g)


def transform_polygon_to_mm(poly_m: Polygon, scaler: ModelScaler, simplify_tolerance_m: float = 0.0) -> Polygon | None:
    if simplify_tolerance_m > 0:
        poly_m = poly_m.simplify(simplify_tolerance_m, preserve_topology=True)
    if poly_m.is_empty:
        return None
    exterior = [scaler.xy_to_mm(float(x), float(y)) for x, y in poly_m.exterior.coords]
    holes = [[scaler.xy_to_mm(float(x), float(y)) for x, y in ring.coords] for ring in poly_m.interiors]
    try:
        poly = Polygon(exterior, holes)
    except Exception:
        return None
    if not poly.is_valid:
        poly = make_valid(poly)
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda p: p.area)
    if not isinstance(poly, Polygon) or poly.is_empty or poly.area < 1e-5:
        return None
    return poly


def parse_height_m(tags: dict[str, str], params: ModelParams) -> float:
    for key in ("height", "building:height"):
        if key in tags:
            text = tags[key].lower().strip()
            match = re.search(r"[-+]?\d*\.?\d+", text)
            if match:
                value = float(match.group(0))
                if "ft" in text or "feet" in text:
                    value *= 0.3048
                if 0.3 <= value <= 900:
                    return value
    for key in ("building:levels", "levels"):
        if key in tags:
            match = re.search(r"[-+]?\d*\.?\d+", tags[key])
            if match:
                levels = float(match.group(0))
                if 0.5 <= levels <= 200:
                    return levels * params.level_height_m
    if tags.get("building") == "roof" or tags.get("building:part") == "roof":
        return 1.0
    return params.default_building_height_m


def parse_length_m(text: str, min_m: float = 0.0, max_m: float = 100.0) -> float | None:
    value = str(text).lower().strip()
    if not value:
        return None

    feet_match = re.search(
        r"([-+]?\d*\.?\d+)\s*(?:'|ft|feet|foot)\s*(?:(\d*\.?\d+)\s*(?:\"|in|inch|inches))?",
        value,
    )
    if feet_match:
        feet = float(feet_match.group(1))
        inches = float(feet_match.group(2) or 0.0)
        parsed = (feet + inches / 12.0) * 0.3048
        return parsed if min_m <= parsed <= max_m else None

    inch_match = re.search(r"([-+]?\d*\.?\d+)\s*(?:\"|in|inch|inches)\b", value)
    if inch_match:
        parsed = float(inch_match.group(1)) * 0.0254
        return parsed if min_m <= parsed <= max_m else None

    match = re.search(r"[-+]?\d*\.?\d+", value)
    if not match:
        return None
    parsed = float(match.group(0))
    if "cm" in value:
        parsed /= 100.0
    elif "mm" in value:
        parsed /= 1000.0
    return parsed if min_m <= parsed <= max_m else None


def build_building_meshes(features: list[OSMFeature], scaler: ModelScaler, terrain: TerrainGrid, params: ModelParams) -> MeshPart:
    parts: list[MeshPart] = []
    tol_m = scaler.length_mm_to_m(params.simplify_tolerance_mm)
    for feature in features:
        if feature.tags.get("underground") == "yes" or feature.tags.get("location") == "underground":
            continue
        for poly_m in iter_polygons(feature.geometry_m):
            poly = transform_polygon_to_mm(poly_m, scaler, tol_m)
            if poly is None:
                continue
            centroid = poly.representative_point()
            z0 = terrain.sample_z(centroid.x, centroid.y)
            h_m = parse_height_m(feature.tags, params)
            h_mm = h_m * scaler.scale_mm_per_m * params.building_height_multiplier
            h_mm = float(np.clip(h_mm, params.min_building_height_mm, params.max_building_height_mm))
            parts.append(extrude_polygon(poly, z0, z0 + h_mm, "building", COLORS["buildings"]))
    return merge_parts("buildings", parts, COLORS["buildings"])


def road_width_m(tags: dict[str, str]) -> float:
    if "width" in tags:
        value = parse_length_m(tags["width"], min_m=0.3, max_m=80.0)
        if value is not None:
            return value
    highway = tags.get("highway", "")
    widths = {
        "motorway": 14.0,
        "trunk": 12.0,
        "primary": 10.0,
        "secondary": 8.0,
        "tertiary": 6.0,
        "unclassified": 4.5,
        "residential": 4.0,
        "living_street": 3.2,
        "service": 3.0,
        "pedestrian": 3.0,
        "track": 2.4,
        "cycleway": 2.0,
        "footway": 1.6,
        "path": 1.4,
        "steps": 1.2,
    }
    return widths.get(highway, 3.5)


def road_width_mm(tags: dict[str, str], scaler: ModelScaler, params: ModelParams) -> float:
    highway = tags.get("highway", "")
    if highway == "footway":
        return params.footway_width_mm
    if highway == "pedestrian":
        return params.pedestrian_width_mm
    return max(scaler.length_m_to_mm(road_width_m(tags)), params.min_road_width_mm)


def is_roundabout(tags: dict[str, str]) -> bool:
    return tags.get("junction") in {"roundabout", "circular"}


def _layer_value(tags: dict[str, str]) -> float:
    text = str(tags.get("layer", "")).strip()
    if not text:
        return 0.0
    match = re.search(r"[-+]?\d*\.?\d+", text)
    if not match:
        return 0.0
    try:
        return float(match.group(0))
    except ValueError:
        return 0.0


def is_bridge(tags: dict[str, str]) -> bool:
    bridge_value = str(tags.get("bridge", "")).strip().lower()
    if bridge_value and bridge_value not in {"no", "false", "0", "none"}:
        return True
    if tags.get("man_made") == "bridge":
        return True
    return _layer_value(tags) > 0


def is_tunnel(tags: dict[str, str]) -> bool:
    tunnel_value = str(tags.get("tunnel", "")).strip().lower()
    return bool(tunnel_value and tunnel_value not in {"no", "false", "0", "none"})


def _roundabout_width_mm(line_m: LineString, tags: dict[str, str], scaler: ModelScaler, params: ModelParams) -> float:
    width_mm = road_width_mm(tags, scaler, params)
    if line_m.is_ring and line_m.length > 0:
        radius_mm = scaler.length_m_to_mm(line_m.length / (2.0 * math.pi))
        if radius_mm > 0.25:
            target_inner_radius_mm = min(max(radius_mm * 0.35, 0.18), radius_mm * 0.65)
            max_width_mm = max(0.20, 2.0 * (radius_mm - target_inner_radius_mm))
            width_mm = min(width_mm, max_width_mm)
        elif radius_mm > 0:
            width_mm = min(width_mm, max(0.12, radius_mm))
    return max(0.12, width_mm)


def _densify_line_coords_m(coords: list[tuple[float, float]], max_step_m: float) -> list[tuple[float, float]]:
    if len(coords) < 2 or max_step_m <= 0:
        return coords
    out: list[tuple[float, float]] = []
    for p0, p1 in zip(coords, coords[1:]):
        if not out:
            out.append((float(p0[0]), float(p0[1])))
        length = math.hypot(float(p1[0]) - float(p0[0]), float(p1[1]) - float(p0[1]))
        steps = max(1, int(math.ceil(length / max_step_m)))
        for step in range(1, steps + 1):
            t = step / steps
            out.append((
                float(p0[0]) + (float(p1[0]) - float(p0[0])) * t,
                float(p0[1]) + (float(p1[1]) - float(p0[1])) * t,
            ))
    return out


def _road_segment_part(
    p0: tuple[float, float],
    p1: tuple[float, float],
    width_mm: float,
    terrain: TerrainGrid,
    thickness_mm: float,
    z_offset_mm: float,
    bridge_offset_mm: float = 0.0,
) -> MeshPart:
    x0, y0 = p0
    x1, y1 = p1
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length < max(0.10, width_mm * 0.15):
        return MeshPart("road", np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), COLORS["roads"])

    nx = -dy / length
    ny = dx / length
    half = width_mm / 2.0
    corners = [
        (x0 + nx * half, y0 + ny * half),
        (x1 + nx * half, y1 + ny * half),
        (x1 - nx * half, y1 - ny * half),
        (x0 - nx * half, y0 - ny * half),
    ]
    bottom_z = np.asarray(
        [terrain.sample_z(x, y) + z_offset_mm + bridge_offset_mm for x, y in corners],
        dtype=float,
    )
    top_z = bottom_z + thickness_mm

    vertices = np.asarray(
        [(x, y, z) for (x, y), z in zip(corners, top_z)] + [(x, y, z) for (x, y), z in zip(corners, bottom_z)],
        dtype=float,
    )
    faces = np.asarray([
        (0, 1, 2), (0, 2, 3),
        (4, 6, 5), (4, 7, 6),
        (0, 4, 5), (0, 5, 1),
        (1, 5, 6), (1, 6, 2),
        (2, 6, 7), (2, 7, 3),
        (3, 7, 4), (3, 4, 0),
    ], dtype=np.int64)
    return MeshPart("road", vertices, faces, COLORS["roads"]).cleaned()


def _crosses_water_cutout(line_m: LineString, water_union_m: BaseGeometry | None) -> bool:
    if water_union_m is None or water_union_m.is_empty:
        return False
    try:
        return bool(line_m.intersects(water_union_m))
    except Exception:
        return False


def build_road_meshes(
    features: list[OSMFeature],
    scaler: ModelScaler,
    terrain: TerrainGrid,
    params: ModelParams,
    water_union_m: BaseGeometry | None = None,
) -> MeshPart:
    parts: list[MeshPart] = []
    tol_m = scaler.length_mm_to_m(max(params.simplify_tolerance_mm, 0.20))
    for feature in features:
        for line_m in iter_lines(feature.geometry_m):
            roundabout = is_roundabout(feature.tags)
            if tol_m > 0:
                roundabout_tol_m = scaler.length_mm_to_m(min(params.simplify_tolerance_mm, 0.03))
                line_m = line_m.simplify(roundabout_tol_m if roundabout else tol_m, preserve_topology=roundabout)
            coords_m = list(line_m.coords)
            if len(coords_m) < 2:
                continue
            if roundabout:
                coords_mm = [scaler.xy_to_mm(float(x), float(y)) for x, y in coords_m]
                line_mm = LineString(coords_mm)
                width_mm = _roundabout_width_mm(line_m, feature.tags, scaler, params)
                elevated = params.bridge_clearance_mm if (
                    params.cut_out_water and not is_tunnel(feature.tags) and _crosses_water_cutout(line_m, water_union_m)
                ) else 0.0
                try:
                    buffered = line_mm.buffer(width_mm / 2.0, cap_style=1, join_style=1)
                except Exception:
                    buffered = GeometryCollection()
                roundabout_part = make_layer_mesh_mm(
                    "roads",
                    iter_polygons(buffered),
                    terrain,
                    thickness_mm=0.50,
                    z_offset_mm=0.12 + elevated,
                    color=COLORS["roads"],
                )
                if not roundabout_part.is_empty():
                    parts.append(roundabout_part)
                continue
            if _terrain_has_relief(terrain):
                max_step_m = scaler.length_mm_to_m(_terrain_spacing_mm(terrain) * 1.5)
                coords_m = _densify_line_coords_m(coords_m, max(max_step_m, 2.0))
            coords_mm = [scaler.xy_to_mm(float(x), float(y)) for x, y in coords_m]
            width_mm = road_width_mm(feature.tags, scaler, params)
            for m0, m1, p0, p1 in zip(coords_m, coords_m[1:], coords_mm, coords_mm[1:]):
                segment_m = LineString([m0, m1])
                elevated = params.bridge_clearance_mm if (
                    params.cut_out_water and not is_tunnel(feature.tags) and _crosses_water_cutout(segment_m, water_union_m)
                ) else 0.0
                parts.append(_road_segment_part(
                    p0,
                    p1,
                    width_mm,
                    terrain,
                    thickness_mm=0.50,
                    z_offset_mm=0.12,
                    bridge_offset_mm=elevated,
                ))
    return merge_parts("roads", parts, COLORS["roads"])


def water_line_width_m(tags: dict[str, str]) -> float:
    waterway = tags.get("waterway", "")
    widths = {"river": 12.0, "canal": 8.0, "stream": 2.5, "ditch": 1.8, "drain": 1.5}
    if "width" in tags:
        value = parse_length_m(tags["width"], min_m=0.5, max_m=100.0)
        if value is not None:
            return value
    return widths.get(waterway, 2.5)


def aeroway_width_m(tags: dict[str, str]) -> float:
    if "width" in tags:
        value = parse_length_m(tags["width"], min_m=1.0, max_m=120.0)
        if value is not None:
            return value
    aeroway = tags.get("aeroway", "")
    widths = {"runway": 35.0, "taxiway": 12.0, "apron": 25.0}
    return widths.get(aeroway, 12.0)


def _buffer_feature_lines(features: list[OSMFeature], scaler: ModelScaler, params: ModelParams, kind: str) -> list[Polygon]:
    polys: list[Polygon] = []
    min_m = scaler.length_mm_to_m(params.min_road_width_mm)
    for feature in features:
        for line in iter_lines(feature.geometry_m):
            if kind == "road":
                width = scaler.length_mm_to_m(road_width_mm(feature.tags, scaler, params))
            elif kind == "airport":
                width = aeroway_width_m(feature.tags)
            else:
                width = max(water_line_width_m(feature.tags), min_m)
            try:
                buffered = line.buffer(width / 2.0, cap_style=2, join_style=2)
            except Exception:
                continue
            for p in iter_polygons(buffered):
                polys.append(p)
    return polys


def _feature_polygons(features: list[OSMFeature]) -> list[Polygon]:
    polys: list[Polygon] = []
    for feature in features:
        for p in iter_polygons(feature.geometry_m):
            polys.append(p)
    return polys


def water_cutout_polygons_mm(water_features: list[OSMFeature], scaler: ModelScaler, params: ModelParams) -> list[Polygon]:
    polygons_m = _feature_polygons(water_features) + _buffer_feature_lines(water_features, scaler, params, "water")
    cutouts: list[Polygon] = []
    for poly_m in polygons_m:
        poly = transform_polygon_to_mm(poly_m, scaler, scaler.length_mm_to_m(params.simplify_tolerance_mm))
        if poly is None:
            continue
        cutouts.extend(list(iter_polygons(poly)))
    return cutouts


def make_layer_mesh(
    name: str,
    polygons_m: Iterable[Polygon],
    scaler: ModelScaler,
    terrain: TerrainGrid,
    params: ModelParams,
    thickness_mm: float,
    z_offset_mm: float,
    color: tuple[int, int, int, int],
    simplify_tolerance_mm: float | None = None,
) -> MeshPart:
    parts: list[MeshPart] = []
    tol_m = scaler.length_mm_to_m(params.simplify_tolerance_mm if simplify_tolerance_mm is None else simplify_tolerance_mm)
    for poly_m in polygons_m:
        poly = transform_polygon_to_mm(poly_m, scaler, tol_m)
        if poly is None:
            continue
        parts.append(extrude_polygon_on_terrain(poly, terrain, z_offset_mm, thickness_mm, name, color))
    return merge_parts(name, parts, color)


def make_layer_mesh_mm(
    name: str,
    polygons_mm: Iterable[Polygon],
    terrain: TerrainGrid,
    thickness_mm: float,
    z_offset_mm: float,
    color: tuple[int, int, int, int],
) -> MeshPart:
    parts: list[MeshPart] = []
    for poly in polygons_mm:
        poly = _clean_polygon(poly)
        if poly is None:
            continue
        parts.append(extrude_polygon_on_terrain(poly, terrain, z_offset_mm, thickness_mm, name, color))
    return merge_parts(name, parts, color)


def build_surface_layer_meshes(
    road_features: list[OSMFeature],
    water_features: list[OSMFeature],
    green_features: list[OSMFeature],
    parking_features: list[OSMFeature],
    airport_features: list[OSMFeature],
    scaler: ModelScaler,
    terrain: TerrainGrid,
    params: ModelParams,
) -> list[MeshPart]:
    parts: list[MeshPart] = []

    water_polys = _feature_polygons(water_features) + _buffer_feature_lines(water_features, scaler, params, "water")
    green_polys = _feature_polygons(green_features)
    parking_polys = _feature_polygons(parking_features)
    airport_polys = _feature_polygons(airport_features) + _buffer_feature_lines(airport_features, scaler, params, "airport")

    water_union = unary_union(water_polys) if water_polys else None
    road_cutout_union = unary_union(_buffer_feature_lines(road_features, scaler, params, "road")) if road_features else None
    parking_union = unary_union(parking_polys) if parking_polys else None
    airport_union = unary_union(airport_polys) if airport_polys else None

    cleaned_parking: list[Polygon] = []
    for pp in parking_polys:
        geom: BaseGeometry = pp
        if water_union and not water_union.is_empty:
            geom = geom.difference(water_union)
        if params.include_airport and airport_union and not airport_union.is_empty:
            geom = geom.difference(airport_union)
        if road_cutout_union and not road_cutout_union.is_empty:
            geom = geom.difference(road_cutout_union)
        cleaned_parking.extend(list(iter_polygons(geom)))

    cleaned_airport: list[Polygon] = []
    for ap in airport_polys:
        geom: BaseGeometry = ap
        if water_union and not water_union.is_empty:
            geom = geom.difference(water_union)
        cleaned_airport.extend(list(iter_polygons(geom)))

    # Green is deliberately lower priority than water, parking, and roads.
    cleaned_green: list[Polygon] = []
    for gp in green_polys:
        geom: BaseGeometry = gp
        if water_union and not water_union.is_empty:
            geom = geom.difference(water_union)
        if params.include_parking and parking_union and not parking_union.is_empty:
            geom = geom.difference(parking_union)
        if params.include_airport and airport_union and not airport_union.is_empty:
            geom = geom.difference(airport_union)
        if road_cutout_union and not road_cutout_union.is_empty:
            geom = geom.difference(road_cutout_union)
        cleaned_green.extend(list(iter_polygons(geom)))

    surface_tol_mm = min(params.simplify_tolerance_mm, 0.03)
    if params.include_green:
        parts.append(make_layer_mesh("green", cleaned_green, scaler, terrain, params, thickness_mm=0.25, z_offset_mm=0.05, color=COLORS["green"], simplify_tolerance_mm=surface_tol_mm))
    if params.include_parking:
        parts.append(make_layer_mesh("parking", cleaned_parking, scaler, terrain, params, thickness_mm=0.20, z_offset_mm=0.06, color=COLORS["parking"], simplify_tolerance_mm=surface_tol_mm))
    if params.include_airport:
        parts.append(make_layer_mesh("airport", cleaned_airport, scaler, terrain, params, thickness_mm=0.20, z_offset_mm=0.06, color=COLORS["airport"], simplify_tolerance_mm=surface_tol_mm))
    if params.include_water and not params.cut_out_water:
        parts.append(make_layer_mesh("water", list(iter_polygons(water_union)) if water_union else [], scaler, terrain, params, thickness_mm=0.35, z_offset_mm=0.08, color=COLORS["water"], simplify_tolerance_mm=surface_tol_mm))
    if params.include_roads:
        parts.append(build_road_meshes(road_features, scaler, terrain, params, water_union if params.cut_out_water else None))

    return parts
