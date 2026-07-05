from __future__ import annotations

from collections.abc import Callable, Iterable
import math
import re
import numpy as np

from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from shapely.geometry.base import BaseGeometry
from shapely.affinity import scale as scale_geometry
from shapely import constrained_delaunay_triangles
from shapely.ops import triangulate, unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree
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
    "area_infill": (176, 164, 138, 255),
    "landmark": (245, 245, 245, 255),
    "route": (220, 58, 48, 255),
    "rail_lines": (72, 72, 72, 255),
    "rail_stations": (214, 214, 206, 255),
    "subway_lines": (170, 55, 170, 255),
    "subway_stations": (205, 180, 230, 255),
}

MIN_PRINTABLE_HOLE_AREA_MM2 = 1e-3
MAX_TOUCHING_HOLE_AREA_MM2 = 10.0
HOLE_TOUCH_PRECISION_MM = 1e-6
AREA_INFILL_PARENT_MIN_AREA_M2 = 1_000_000.0
AREA_INFILL_PARENT_LARGE_MAP_MIN_AREA_M2 = 20_000_000.0
AREA_INFILL_PARENT_MIN_SELECTION_FRACTION = 0.015
AREA_INFILL_PARENT_ROAD_RATIO = 0.006
AREA_INFILL_PARENT_DETAIL_RATIO = 0.08
AREA_INFILL_PARENT_CHILD_RATIO = 0.015
AREA_INFILL_PARENT_CHILD_COUNT = 3


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


VertexCache = dict[tuple[int, int, int], int]


def _vertex_key(x: float, y: float, z: float, precision: float = 1e-6) -> tuple[int, int, int]:
    return (
        int(round(float(x) / precision)),
        int(round(float(y) / precision)),
        int(round(float(z) / precision)),
    )


def _vertex_id(vertices: list[tuple[float, float, float]], cache: VertexCache, x: float, y: float, z: float) -> int:
    key = _vertex_key(x, y, z)
    existing = cache.get(key)
    if existing is not None:
        return existing
    idx = len(vertices)
    vertices.append((float(x), float(y), float(z)))
    cache[key] = idx
    return idx


def _add_triangle(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    cache: VertexCache,
    coords: list[tuple[float, float]],
    z: float,
    up: bool,
) -> None:
    if len(coords) < 3:
        return
    tri = coords[:3]
    area = _signed_area(tri + [tri[0]])
    if abs(area) <= 1e-12:
        return
    idx = [_vertex_id(vertices, cache, x, y, z) for x, y in tri]
    if up:
        faces.append((idx[0], idx[1], idx[2]) if area >= 0 else (idx[0], idx[2], idx[1]))
    else:
        faces.append((idx[0], idx[2], idx[1]) if area >= 0 else (idx[0], idx[1], idx[2]))


def _add_ring_sides(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    cache: VertexCache,
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
        idx = (
            _vertex_id(vertices, cache, p0[0], p0[1], z0),
            _vertex_id(vertices, cache, p1[0], p1[1], z0),
            _vertex_id(vertices, cache, p1[0], p1[1], z1),
            _vertex_id(vertices, cache, p0[0], p0[1], z1),
        )
        if not reverse:
            faces.append((idx[0], idx[1], idx[2]))
            faces.append((idx[0], idx[2], idx[3]))
        else:
            faces.append((idx[0], idx[2], idx[1]))
            faces.append((idx[0], idx[3], idx[2]))


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
    poly = _drop_tiny_holes(poly)
    return poly


def _ring_point_keys(ring: Iterable[tuple[float, float]], precision: float = HOLE_TOUCH_PRECISION_MM) -> set[tuple[int, int]]:
    keys: set[tuple[int, int]] = set()
    coords = list(ring)
    points = coords[:-1] if len(coords) > 1 and coords[0] == coords[-1] else coords
    for x, y in points:
        keys.add((int(round(float(x) / precision)), int(round(float(y) / precision))))
    return keys


def _drop_tiny_holes(
    poly: Polygon,
    min_hole_area: float = MIN_PRINTABLE_HOLE_AREA_MM2,
    max_touching_hole_area: float = MAX_TOUCHING_HOLE_AREA_MM2,
) -> Polygon:
    if not poly.interiors:
        return poly
    exterior_keys = _ring_point_keys(poly.exterior.coords)
    hole_keys = [_ring_point_keys(ring.coords) for ring in poly.interiors]
    holes: list[list[tuple[float, float]]] = []
    changed = False
    for index, ring in enumerate(poly.interiors):
        try:
            hole_area = abs(Polygon(ring).area)
        except Exception:
            changed = True
            continue
        touches_other_boundary = bool(hole_keys[index] & exterior_keys)
        if not touches_other_boundary and hole_area <= max_touching_hole_area:
            touches_other_boundary = any(
                bool(hole_keys[index] & other_keys)
                for other_index, other_keys in enumerate(hole_keys)
                if other_index != index
            )
        if hole_area <= min_hole_area:
            changed = True
            continue
        if touches_other_boundary and hole_area <= max_touching_hole_area:
            changed = True
            continue
        holes.append([(float(x), float(y)) for x, y in ring.coords])
    if not changed:
        return poly
    try:
        cleaned = Polygon([(float(x), float(y)) for x, y in poly.exterior.coords], holes)
    except Exception:
        return poly
    if cleaned.is_empty:
        return poly
    if not cleaned.is_valid:
        valid = make_valid(cleaned)
        if isinstance(valid, MultiPolygon):
            valid = max(valid.geoms, key=lambda g: g.area)
        if isinstance(valid, Polygon) and not valid.is_empty:
            return valid
        return poly
    return cleaned


def extrude_polygon(poly: Polygon, z0: float, z1: float, name: str, color: tuple[int, int, int, int]) -> MeshPart:
    poly = _clean_polygon(poly)  # type: ignore[assignment]
    if poly is None or z1 <= z0:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    cache: VertexCache = {}

    for tri in _triangulate_polygon(poly):
        coords = [(float(x), float(y)) for x, y in list(tri.exterior.coords)[:3]]
        _add_triangle(vertices, faces, cache, coords, z1, up=True)
        _add_triangle(vertices, faces, cache, coords, z0, up=False)

    _add_ring_sides(vertices, faces, cache, [(float(x), float(y)) for x, y in poly.exterior.coords], z0, z1, reverse=False)
    for interior in poly.interiors:
        _add_ring_sides(vertices, faces, cache, [(float(x), float(y)) for x, y in interior.coords], z0, z1, reverse=True)

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
    cache: VertexCache,
    top_faces: list[tuple[int, int, int]],
    top_to_bottom: dict[int, int],
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
    top_idx = [_vertex_id(vertices, cache, x, y, z) for (x, y), z in zip(tri, top)]
    bottom_idx = [_vertex_id(vertices, cache, x, y, z) for (x, y), z in zip(tri, bottom)]
    for top_vertex, bottom_vertex in zip(top_idx, bottom_idx):
        top_to_bottom[top_vertex] = bottom_vertex
    if area >= 0:
        top_face = (top_idx[0], top_idx[1], top_idx[2])
        faces.append(top_face)
        top_faces.append(top_face)
        faces.append((bottom_idx[0], bottom_idx[2], bottom_idx[1]))
    else:
        top_face = (top_idx[0], top_idx[2], top_idx[1])
        faces.append(top_face)
        top_faces.append(top_face)
        faces.append((bottom_idx[0], bottom_idx[1], bottom_idx[2]))


def _add_terrain_ring_sides(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    cache: VertexCache,
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
        idx = (
            _vertex_id(vertices, cache, p0[0], p0[1], b0),
            _vertex_id(vertices, cache, p1[0], p1[1], b1),
            _vertex_id(vertices, cache, p1[0], p1[1], b1 + thickness_mm),
            _vertex_id(vertices, cache, p0[0], p0[1], b0 + thickness_mm),
        )
        if not reverse:
            faces.append((idx[0], idx[1], idx[2]))
            faces.append((idx[0], idx[2], idx[3]))
        else:
            faces.append((idx[0], idx[2], idx[1]))
            faces.append((idx[0], idx[3], idx[2]))


def _add_boundary_sides_from_top_faces(
    faces: list[tuple[int, int, int]],
    top_faces: list[tuple[int, int, int]],
    top_to_bottom: dict[int, int],
) -> None:
    edge_uses: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for a, b, c in top_faces:
        for edge in ((a, b), (b, c), (c, a)):
            key = tuple(sorted(edge))
            edge_uses.setdefault(key, []).append(edge)

    for uses in edge_uses.values():
        if len(uses) != 1:
            continue
        a, b = uses[0]
        bottom_a = top_to_bottom.get(a)
        bottom_b = top_to_bottom.get(b)
        if bottom_a is None or bottom_b is None or bottom_a == bottom_b:
            continue
        faces.append((a, b, bottom_b))
        faces.append((a, bottom_b, bottom_a))


def _sample_building_bottom_points(poly: Polygon, terrain: TerrainGrid) -> list[tuple[float, float]]:
    spacing = _terrain_spacing_mm(terrain)
    max_step = max(0.5, spacing)
    points: list[tuple[float, float]] = []
    exterior = _densify_ring_xy(poly.exterior.coords, max_step)
    points.extend(exterior[:-1])
    for ring in poly.interiors:
        hole = _densify_ring_xy(ring.coords, max_step)
        points.extend(hole[:-1])
    points.extend(_terrain_points_inside_polygon(poly, terrain, max_points=1500))
    return _dedupe_xy(points)


def _building_roof_z(bottom_z: list[float], height_mm: float) -> float:
    if not bottom_z:
        return height_mm
    bottom = np.asarray(bottom_z, dtype=float)
    baseline = float(np.median(bottom))
    min_wall_height = min(1.0, max(0.25, height_mm * 0.15))
    return max(baseline + height_mm, float(np.max(bottom)) + min_wall_height)


def _add_building_terrain_triangle(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    cache: VertexCache,
    top_faces: list[tuple[int, int, int]],
    top_to_bottom: dict[int, int],
    coords: list[tuple[float, float]],
    terrain: TerrainGrid,
    roof_z: float,
    bottom_offset_mm: float = 0.0,
) -> None:
    if len(coords) < 3:
        return
    tri = coords[:3]
    area = _signed_area(tri + [tri[0]])
    if abs(area) <= 1e-12:
        return
    bottom = [terrain.sample_z(x, y) + bottom_offset_mm for x, y in tri]
    top_idx = [_vertex_id(vertices, cache, x, y, roof_z) for x, y in tri]
    bottom_idx = [_vertex_id(vertices, cache, x, y, z) for (x, y), z in zip(tri, bottom)]
    for top_vertex, bottom_vertex in zip(top_idx, bottom_idx):
        top_to_bottom[top_vertex] = bottom_vertex
    if area >= 0:
        top_face = (top_idx[0], top_idx[1], top_idx[2])
        faces.append(top_face)
        top_faces.append(top_face)
        faces.append((bottom_idx[0], bottom_idx[2], bottom_idx[1]))
    else:
        top_face = (top_idx[0], top_idx[2], top_idx[1])
        faces.append(top_face)
        top_faces.append(top_face)
        faces.append((bottom_idx[0], bottom_idx[1], bottom_idx[2]))


def extrude_building_on_terrain(
    poly: Polygon,
    terrain: TerrainGrid,
    height_mm: float,
    name: str,
    color: tuple[int, int, int, int],
    min_height_mm: float = 0.0,
) -> MeshPart:
    poly = _clean_polygon(poly)  # type: ignore[assignment]
    if poly is None or height_mm <= 0:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    min_height_mm = max(0.0, min(float(min_height_mm), max(0.0, height_mm - 0.05)))
    if not _terrain_has_relief(terrain):
        point = poly.representative_point()
        z0 = terrain.sample_z(point.x, point.y)
        return extrude_polygon(poly, z0 + min_height_mm, z0 + height_mm, name, color)

    points = _sample_building_bottom_points(poly, terrain)
    if len(points) < 3:
        point = poly.representative_point()
        z0 = terrain.sample_z(point.x, point.y)
        return extrude_polygon(poly, z0, z0 + height_mm, name, color)

    terrain_z = [terrain.sample_z(x, y) for x, y in points]
    bottom_z = [z + min_height_mm for z in terrain_z]
    roof_z = max(_building_roof_z(terrain_z, height_mm), max(bottom_z) + 0.05)

    try:
        candidates = triangulate(MultiPoint(points))
    except Exception:
        candidates = []
    if not candidates:
        candidates = _triangulate_polygon(poly)

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    cache: VertexCache = {}
    top_faces: list[tuple[int, int, int]] = []
    top_to_bottom: dict[int, int] = {}
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
                _add_building_terrain_triangle(
                    vertices,
                    faces,
                    cache,
                    top_faces,
                    top_to_bottom,
                    coords,
                    terrain,
                    roof_z,
                    bottom_offset_mm=min_height_mm,
                )

    _add_boundary_sides_from_top_faces(faces, top_faces, top_to_bottom)

    if not faces:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    return MeshPart(name, np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64), color).cleaned()


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
    cache: VertexCache = {}
    top_faces: list[tuple[int, int, int]] = []
    top_to_bottom: dict[int, int] = {}
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
                _add_terrain_triangle(vertices, faces, cache, top_faces, top_to_bottom, coords, terrain, z_offset_mm, thickness_mm)

    _add_boundary_sides_from_top_faces(faces, top_faces, top_to_bottom)

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


def iter_points(geom: BaseGeometry) -> Iterable[Point]:
    if geom.is_empty:
        return
    if isinstance(geom, Point):
        yield geom
    elif isinstance(geom, MultiPoint):
        for g in geom.geoms:
            yield g
    elif isinstance(geom, GeometryCollection):
        for g in geom.geoms:
            yield from iter_points(g)


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
    poly = _drop_tiny_holes(poly)
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


def parse_min_height_m(tags: dict[str, str], params: ModelParams) -> float:
    for key in ("min_height", "building:min_height"):
        if key in tags:
            parsed = parse_length_m(tags[key], min_m=0.0, max_m=900.0)
            if parsed is not None:
                return parsed
    for key in ("min_level", "min_levels", "building:min_level", "building:min_levels"):
        if key in tags:
            match = re.search(r"[-+]?\d*\.?\d+", str(tags[key]))
            if match:
                levels = float(match.group(0))
                if 0.0 <= levels <= 200:
                    return levels * params.level_height_m
    return 0.0


def parse_roof_height_m(tags: dict[str, str], params: ModelParams, building_height_m: float) -> float | None:
    for key in ("roof:height", "building:roof:height"):
        if key in tags:
            parsed = parse_length_m(tags[key], min_m=0.05, max_m=300.0)
            if parsed is not None:
                return min(parsed, max(0.05, building_height_m * 0.85))
    for key in ("roof:levels", "building:roof:levels"):
        if key in tags:
            match = re.search(r"[-+]?\d*\.?\d+", str(tags[key]))
            if match:
                levels = float(match.group(0))
                if 0.05 <= levels <= 80:
                    return min(levels * params.level_height_m, max(0.05, building_height_m * 0.85))
    return None


def _is_high_detail_mode(params: ModelParams) -> bool:
    return getattr(params, "model_detail_mode", "normal") == "high"


ROOF_SHAPE_ALIASES = {
    "gable": "gabled",
    "gable_roof": "gabled",
    "half-hip": "hipped",
    "half_hipped": "hipped",
    "pyramid": "pyramidal",
    "shed": "skillion",
    "lean_to": "skillion",
    "round": "dome",
    "hemispherical": "dome",
    "spherical": "dome",
    "onion": "dome",
    "mansard": "hipped",
    "gambrel": "gabled",
    "saltbox": "gabled",
}
SUPPORTED_OSM_ROOF_SHAPES = {"gabled", "hipped", "pyramidal", "skillion", "dome"}


def roof_shape_from_tags(tags: dict[str, str]) -> str | None:
    raw = str(tags.get("roof:shape") or tags.get("building:roof:shape") or "").strip().lower()
    if not raw:
        return None
    raw = raw.replace(" ", "_")
    shape = ROOF_SHAPE_ALIASES.get(raw, raw)
    if shape in {"flat", "none"}:
        return None
    return shape if shape in SUPPORTED_OSM_ROOF_SHAPES else None


def _printable_roof_shape_from_tags(tags: dict[str, str]) -> str | None:
    shape = roof_shape_from_tags(tags)
    if shape == "skillion" and "building:part" in tags:
        return None
    return shape


def _is_building_part_feature(feature: OSMFeature) -> bool:
    return "building:part" in feature.tags


def _is_monument_feature(tags: dict[str, str]) -> bool:
    historic = tags.get("historic")
    memorial = tags.get("memorial")
    return historic in {"monument", "memorial"} or memorial in {"stele", "obelisk", "statue"}


def _feature_polygons_single(feature: OSMFeature) -> list[Polygon]:
    return [poly for poly in iter_polygons(feature.geometry_m) if not poly.is_empty and poly.area > 1e-6]


def _overlaps_building_parts(feature: OSMFeature, part_polys: list[Polygon], part_tree: STRtree) -> bool:
    polys = _feature_polygons_single(feature)
    if not polys:
        return False
    for poly in polys:
        try:
            candidates = part_tree.query(poly)
        except Exception:
            continue
        overlap_area = 0.0
        for raw_index in candidates:
            try:
                part = part_polys[int(raw_index)]
            except (TypeError, ValueError, IndexError):
                continue
            if part.is_empty or part.area <= 1e-6:
                continue
            try:
                overlap_area += float(poly.intersection(part).area)
            except Exception:
                continue
            if overlap_area / max(poly.area, 1e-6) >= 0.05:
                return True
    return False


def _select_building_features_for_detail(features: list[OSMFeature], params: ModelParams) -> list[OSMFeature]:
    if not _is_high_detail_mode(params):
        return features
    part_features = [feature for feature in features if _is_building_part_feature(feature)]
    part_polys = [poly for feature in part_features for poly in _feature_polygons_single(feature)]
    if not part_polys:
        return features
    part_tree = STRtree(part_polys)
    selected: list[OSMFeature] = []
    for feature in features:
        if _is_building_part_feature(feature) or _is_monument_feature(feature.tags):
            selected.append(feature)
            continue
        if "building" in feature.tags and _overlaps_building_parts(feature, part_polys, part_tree):
            continue
        selected.append(feature)
    return selected


def _scaled_building_poly(poly: Polygon, factor: float) -> Polygon | None:
    try:
        scaled = scale_geometry(poly, xfact=factor, yfact=factor, origin="centroid")
    except Exception:
        return None
    return _clean_polygon(scaled)  # type: ignore[arg-type, return-value]


def _oriented_rectangle_part(poly: Polygon, long_factor: float, short_factor: float) -> Polygon | None:
    try:
        rect = poly.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)[:4]
    except Exception:
        return None
    if len(coords) < 4:
        return _scaled_building_poly(poly, min(long_factor, short_factor))

    edges: list[tuple[float, tuple[float, float]]] = []
    for p0, p1 in zip(coords, coords[1:] + coords[:1]):
        dx = float(p1[0] - p0[0])
        dy = float(p1[1] - p0[1])
        length = math.hypot(dx, dy)
        if length > 1e-9:
            edges.append((length, (dx / length, dy / length)))
    if len(edges) < 2:
        return _scaled_building_poly(poly, min(long_factor, short_factor))

    edges.sort(key=lambda item: item[0], reverse=True)
    long_len, long_axis = edges[0]
    short_len, short_axis = edges[-1]
    center = poly.centroid
    cx = float(center.x)
    cy = float(center.y)
    lu = max(0.05, long_len * long_factor / 2.0)
    sv = max(0.05, short_len * short_factor / 2.0)
    ux, uy = long_axis
    vx, vy = short_axis
    try:
        candidate = Polygon([
            (cx - ux * lu - vx * sv, cy - uy * lu - vy * sv),
            (cx + ux * lu - vx * sv, cy + uy * lu - vy * sv),
            (cx + ux * lu + vx * sv, cy + uy * lu + vy * sv),
            (cx - ux * lu + vx * sv, cy - uy * lu + vy * sv),
        ])
    except Exception:
        return _scaled_building_poly(poly, min(long_factor, short_factor))
    return _clean_polygon(candidate)  # type: ignore[arg-type, return-value]


def _building_top_z_for_height(poly: Polygon, terrain: TerrainGrid, height_mm: float, min_height_mm: float = 0.0) -> float:
    min_height_mm = max(0.0, min(float(min_height_mm), max(0.0, height_mm - 0.05)))
    if not _terrain_has_relief(terrain):
        point = poly.representative_point()
        return terrain.sample_z(point.x, point.y) + height_mm
    points = _sample_building_bottom_points(poly, terrain)
    if not points:
        point = poly.representative_point()
        return terrain.sample_z(point.x, point.y) + height_mm
    terrain_z = [terrain.sample_z(x, y) for x, y in points]
    bottom_z = [z + min_height_mm for z in terrain_z]
    return max(_building_roof_z(terrain_z, height_mm), max(bottom_z) + 0.05)


def _roof_axes(poly: Polygon) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], float, float]:
    center = poly.representative_point()
    cx = float(center.x)
    cy = float(center.y)
    ux, uy = 1.0, 0.0
    vx, vy = 0.0, 1.0
    try:
        rect = poly.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)[:4]
    except Exception:
        coords = []
    if len(coords) >= 4:
        edges: list[tuple[float, tuple[float, float]]] = []
        for p0, p1 in zip(coords, coords[1:] + coords[:1]):
            dx = float(p1[0] - p0[0])
            dy = float(p1[1] - p0[1])
            length = math.hypot(dx, dy)
            if length > 1e-9:
                edges.append((length, (dx / length, dy / length)))
        if edges:
            edges.sort(key=lambda item: item[0], reverse=True)
            ux, uy = edges[0][1]
            vx, vy = -uy, ux
    values_u: list[float] = []
    values_v: list[float] = []
    for x, y in list(poly.exterior.coords)[:-1]:
        dx = float(x) - cx
        dy = float(y) - cy
        values_u.append(dx * ux + dy * uy)
        values_v.append(dx * vx + dy * vy)
    max_u = max(0.05, max((abs(v) for v in values_u), default=0.05))
    max_v = max(0.05, max((abs(v) for v in values_v), default=0.05))
    return (cx, cy), (ux, uy), (vx, vy), max_u, max_v


def _roof_exterior_step(poly: Polygon, shape: str) -> float:
    minx, miny, maxx, maxy = poly.bounds
    span = max(maxx - minx, maxy - miny, 1.0)
    short_span = max(min(maxx - minx, maxy - miny), 0.1)
    if shape == "dome":
        return max(0.25, span / 32.0)
    return max(0.18, min(span / 8.0, short_span / 3.0))


def _roof_sample_points(poly: Polygon, shape: str, axes: tuple[tuple[float, float], tuple[float, float], tuple[float, float], float, float]) -> list[tuple[float, float]]:
    (cx, cy), (ux, uy), _, max_u, _ = axes
    minx, miny, maxx, maxy = poly.bounds
    points: list[tuple[float, float]] = _densify_ring_xy(poly.exterior.coords, _roof_exterior_step(poly, shape))[:-1]
    points.append((cx, cy))
    if shape == "gabled":
        ridge_half = max_u * 0.55
        for t in np.linspace(-ridge_half, ridge_half, 5):
            point = Point(cx + ux * float(t), cy + uy * float(t))
            if poly.buffer(1e-6).covers(point):
                points.append((point.x, point.y))
    if shape == "dome":
        samples = 21
        for ix in range(samples):
            x = minx + (maxx - minx) * (ix + 0.5) / samples
            for iy in range(samples):
                y = miny + (maxy - miny) * (iy + 0.5) / samples
                point = Point(x, y)
                if poly.covers(point):
                    points.append((float(x), float(y)))
    return _dedupe_xy(points, precision=1e-4)


def _roof_top_z_function(
    poly: Polygon,
    shape: str,
    z_base: float,
    z_top: float,
    tags: dict[str, str] | None = None,
) -> Callable[[float, float], float]:
    (cx, cy), (ux, uy), (vx, vy), max_u, max_v = _roof_axes(poly)
    roof_h = max(0.05, z_top - z_base)
    boundary_tol = max(0.02, max(max_u, max_v) * 1e-4)
    roof_direction = _parse_roof_direction(tags or {})
    direction_bounds: tuple[float, float] | None = None
    direction_vector: tuple[float, float] | None = None
    if shape == "skillion" and roof_direction is not None:
        direction_vector = _bearing_to_xy_vector(roof_direction)
        projections = [float(x) * direction_vector[0] + float(y) * direction_vector[1] for x, y in poly.exterior.coords]
        if projections:
            min_projection = min(projections)
            max_projection = max(projections)
            if max_projection > min_projection + 1e-6:
                direction_bounds = (min_projection, max_projection)
    gabled_across = shape == "gabled" and _roof_orientation(tags or {}) == "across"

    def normalized(x: float, y: float) -> tuple[float, float]:
        dx = float(x) - cx
        dy = float(y) - cy
        return (dx * ux + dy * uy) / max_u, (dx * vx + dy * vy) / max_v

    def top_z(x: float, y: float) -> float:
        if direction_bounds is not None and direction_vector is not None:
            projection = float(x) * direction_vector[0] + float(y) * direction_vector[1]
            low, high = direction_bounds
            factor = max(0.0, min(1.0, (projection - low) / (high - low)))
            return z_base + roof_h * factor
        u, v = normalized(x, y)
        if shape == "skillion":
            factor = max(0.0, min(1.0, (u + 1.0) / 2.0))
            return z_base + roof_h * factor
        if shape == "gabled":
            factor = max(0.0, 1.0 - abs(u if gabled_across else v))
            return z_base + roof_h * min(1.0, factor)
        if poly.boundary.distance(Point(float(x), float(y))) <= boundary_tol:
            return z_base
        if shape == "dome":
            r2 = u * u + v * v
            factor = math.sqrt(max(0.0, 1.0 - min(1.0, r2)))
            return z_base + roof_h * factor
        factor = max(0.0, 1.0 - max(abs(u), abs(v)))
        return z_base + roof_h * min(1.0, factor)

    return top_z


def _ring_points_without_close(ring: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for x, y in ring:
        point = (float(x), float(y))
        if not points or math.hypot(point[0] - points[-1][0], point[1] - points[-1][1]) > 1e-6:
            points.append(point)
    if len(points) > 1 and math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) <= 1e-6:
        points.pop()
    return points


def _remove_collinear_ring_points(points: list[tuple[float, float]], tolerance: float = 1e-7) -> list[tuple[float, float]]:
    cleaned = list(points)
    changed = True
    while changed and len(cleaned) > 3:
        changed = False
        next_points: list[tuple[float, float]] = []
        for index, point in enumerate(cleaned):
            prev_point = cleaned[index - 1]
            next_point = cleaned[(index + 1) % len(cleaned)]
            v0 = (point[0] - prev_point[0], point[1] - prev_point[1])
            v1 = (next_point[0] - point[0], next_point[1] - point[1])
            cross = v0[0] * v1[1] - v0[1] * v1[0]
            scale = max(1.0, math.hypot(*v0), math.hypot(*v1))
            if abs(cross) <= tolerance * scale:
                changed = True
                continue
            next_points.append(point)
        cleaned = next_points
    return cleaned


def _is_convex_ring(points: list[tuple[float, float]]) -> bool:
    if len(points) < 3:
        return False
    area = _signed_area(points + [points[0]])
    if abs(area) <= 1e-9:
        return False
    expected = 1.0 if area > 0 else -1.0
    for index, point in enumerate(points):
        prev_point = points[index - 1]
        next_point = points[(index + 1) % len(points)]
        v0 = (point[0] - prev_point[0], point[1] - prev_point[1])
        v1 = (next_point[0] - point[0], next_point[1] - point[1])
        cross = v0[0] * v1[1] - v0[1] * v1[0]
        if abs(cross) <= 1e-9:
            continue
        if cross * expected < -1e-9:
            return False
    return True


def _long_edge_first(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) != 4:
        return points
    edges = [
        math.hypot(points[(index + 1) % 4][0] - points[index][0], points[(index + 1) % 4][1] - points[index][1])
        for index in range(4)
    ]
    if min(edges, default=0.0) <= 1e-6:
        return points
    start = max(range(4), key=lambda index: edges[index])
    return points[start:] + points[:start]


def _roof_quad_frame(poly: Polygon, allow_rectangularize: bool = False) -> list[tuple[float, float]] | None:
    points = _ring_points_without_close(poly.exterior.coords)
    points = _remove_collinear_ring_points(points)
    if len(points) == 4 and _is_convex_ring(points):
        return _long_edge_first(points)
    try:
        rect = poly.minimum_rotated_rectangle
        rect_coords = [(float(x), float(y)) for x, y in list(rect.exterior.coords)[:4]]
        rect_area = abs(Polygon(rect_coords).area)
    except Exception:
        return None
    if len(rect_coords) != 4 or rect_area <= 1e-9:
        return None
    ratio = poly.area / rect_area
    threshold = 0.70 if allow_rectangularize and len(points) <= 8 else 0.90
    if ratio < threshold:
        return None
    return _long_edge_first(rect_coords)


def _parse_roof_direction(tags: dict[str, str]) -> float | None:
    raw = str(tags.get("roof:direction") or tags.get("building:roof:direction") or "").strip().lower()
    if not raw:
        return None
    directions = {
        "n": 0.0,
        "north": 0.0,
        "ne": 45.0,
        "northeast": 45.0,
        "e": 90.0,
        "east": 90.0,
        "se": 135.0,
        "southeast": 135.0,
        "s": 180.0,
        "south": 180.0,
        "sw": 225.0,
        "southwest": 225.0,
        "w": 270.0,
        "west": 270.0,
        "nw": 315.0,
        "northwest": 315.0,
    }
    if raw in directions:
        return directions[raw]
    match = re.search(r"[-+]?\d*\.?\d+", raw)
    if not match:
        return None
    return float(match.group(0)) % 360.0


def _roof_orientation(tags: dict[str, str]) -> str | None:
    raw = str(tags.get("roof:orientation") or tags.get("building:roof:orientation") or "").strip().lower()
    return raw if raw in {"along", "across"} else None


def _bearing_to_xy_vector(bearing_degrees: float) -> tuple[float, float]:
    radians = math.radians(float(bearing_degrees))
    return math.sin(radians), math.cos(radians)


def _rectangle_roof_frame(poly: Polygon) -> tuple[list[tuple[float, float]], float] | None:
    try:
        rect = poly.minimum_rotated_rectangle
        coords = [(float(x), float(y)) for x, y in list(rect.exterior.coords)[:4]]
    except Exception:
        return None
    if len(coords) != 4:
        return None
    try:
        rect_area = abs(Polygon(coords).area)
    except Exception:
        return None
    if rect_area <= 1e-9 or poly.area / rect_area < 0.90:
        return None
    edges = [
        math.hypot(coords[(index + 1) % 4][0] - coords[index][0], coords[(index + 1) % 4][1] - coords[index][1])
        for index in range(4)
    ]
    if min(edges, default=0.0) <= 1e-6:
        return None
    if edges[0] < edges[1]:
        coords = [coords[1], coords[2], coords[3], coords[0]]
        edges = edges[1:] + edges[:1]
    return coords, max(edges)


def _quad_faces(a: int, b: int, c: int, d: int) -> list[tuple[int, int, int]]:
    return [(a, b, c), (a, c, d)]


def _build_rectangular_roof_mesh(
    poly: Polygon,
    z_base: float,
    z_top: float,
    shape: str,
    name: str,
    color: tuple[int, int, int, int],
    include_bottom: bool,
    tags: dict[str, str] | None = None,
) -> MeshPart:
    tags = tags or {}
    direction = _parse_roof_direction(tags)
    coords = _roof_quad_frame(poly, allow_rectangularize=shape == "skillion" and direction is not None)
    if coords is None:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    a, b, c, d = coords
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    cache: VertexCache = {}

    a0 = _vertex_id(vertices, cache, a[0], a[1], z_base)
    b0 = _vertex_id(vertices, cache, b[0], b[1], z_base)
    c0 = _vertex_id(vertices, cache, c[0], c[1], z_base)
    d0 = _vertex_id(vertices, cache, d[0], d[1], z_base)
    if include_bottom:
        faces.extend([(a0, d0, c0), (a0, c0, b0)])

    if shape == "skillion":
        if direction is not None:
            dx, dy = _bearing_to_xy_vector(direction)
            projections = [point[0] * dx + point[1] * dy for point in coords]
            low = min(projections)
            high = max(projections)
            if high > low + 1e-6:
                top_z = [z_base + (z_top - z_base) * max(0.0, min(1.0, (value - low) / (high - low))) for value in projections]
            else:
                top_z = [z_base, z_top, z_top, z_base]
        else:
            top_z = [z_base, z_top, z_top, z_base]
        bottom = [a0, b0, c0, d0]
        top = [
            _vertex_id(vertices, cache, point[0], point[1], z)
            for point, z in zip(coords, top_z)
        ]
        faces.extend(_quad_faces(top[0], top[1], top[2], top[3]))
        for index in range(4):
            next_index = (index + 1) % 4
            b0_edge = bottom[index]
            b1_edge = bottom[next_index]
            t0_edge = top[index]
            t1_edge = top[next_index]
            if t0_edge == b0_edge and t1_edge == b1_edge:
                continue
            if t0_edge == b0_edge:
                faces.append((b0_edge, t1_edge, b1_edge))
            elif t1_edge == b1_edge:
                faces.append((b0_edge, t0_edge, b1_edge))
            else:
                faces.extend(_quad_faces(b0_edge, b1_edge, t1_edge, t0_edge))
    elif shape == "gabled":
        if _roof_orientation(tags or {}) == "across":
            r0 = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            r1 = ((d[0] + c[0]) / 2.0, (d[1] + c[1]) / 2.0)
            r0t = _vertex_id(vertices, cache, r0[0], r0[1], z_top)
            r1t = _vertex_id(vertices, cache, r1[0], r1[1], z_top)
            faces.extend([(a0, d0, r1t), (a0, r1t, r0t)])
            faces.extend([(b0, r0t, r1t), (b0, r1t, c0)])
            faces.append((a0, r0t, b0))
            faces.append((d0, c0, r1t))
        else:
            r0 = ((a[0] + d[0]) / 2.0, (a[1] + d[1]) / 2.0)
            r1 = ((b[0] + c[0]) / 2.0, (b[1] + c[1]) / 2.0)
            r0t = _vertex_id(vertices, cache, r0[0], r0[1], z_top)
            r1t = _vertex_id(vertices, cache, r1[0], r1[1], z_top)
            faces.extend([(a0, b0, r1t), (a0, r1t, r0t)])
            faces.extend([(d0, r0t, r1t), (d0, r1t, c0)])
            faces.append((a0, r0t, d0))
            faces.append((b0, c0, r1t))
    else:
        center = poly.representative_point()
        apex = _vertex_id(vertices, cache, float(center.x), float(center.y), z_top)
        faces.extend([(a0, b0, apex), (b0, c0, apex), (c0, d0, apex), (d0, a0, apex)])

    if not faces:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    return MeshPart(name, np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64), color).cleaned()


def _ray_boundary_point(poly: Polygon, cx: float, cy: float, angle: float) -> tuple[float, float] | None:
    minx, miny, maxx, maxy = poly.bounds
    radius = max(maxx - minx, maxy - miny, 1.0) * 2.5
    dx = math.cos(angle)
    dy = math.sin(angle)
    ray = LineString([(cx, cy), (cx + dx * radius, cy + dy * radius)])
    try:
        intersection = poly.boundary.intersection(ray)
    except Exception:
        return None
    points: list[Point] = []
    if isinstance(intersection, Point):
        points = [intersection]
    elif isinstance(intersection, MultiPoint):
        points = list(intersection.geoms)
    elif isinstance(intersection, (LineString, MultiLineString, GeometryCollection)):
        for geom in getattr(intersection, "geoms", [intersection]):
            if isinstance(geom, Point):
                points.append(geom)
            elif isinstance(geom, LineString):
                coords = list(geom.coords)
                if coords:
                    points.extend(Point(float(x), float(y)) for x, y in (coords[0], coords[-1]))
    if not points:
        return None
    point = max(points, key=lambda p: (float(p.x) - cx) * dx + (float(p.y) - cy) * dy)
    return float(point.x), float(point.y)


def _build_dome_roof_mesh(
    poly: Polygon,
    z_base: float,
    z_top: float,
    name: str,
    color: tuple[int, int, int, int],
    include_bottom: bool,
) -> MeshPart:
    center = poly.representative_point()
    cx = float(center.x)
    cy = float(center.y)
    angle_count = 96
    ring_count = 32
    boundary: list[tuple[float, float]] = []
    for index in range(angle_count):
        point = _ray_boundary_point(poly, cx, cy, math.tau * index / angle_count)
        if point is None:
            return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
        boundary.append(point)

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    cache: VertexCache = {}
    top_center = _vertex_id(vertices, cache, cx, cy, z_top)
    bottom_center = _vertex_id(vertices, cache, cx, cy, z_base)
    rings: list[list[int]] = []
    for ring in range(1, ring_count + 1):
        fraction = ring / ring_count
        z = z_base + (z_top - z_base) * math.sqrt(max(0.0, 1.0 - fraction * fraction))
        ring_vertices: list[int] = []
        for bx, by in boundary:
            x = cx + (bx - cx) * fraction
            y = cy + (by - cy) * fraction
            ring_vertices.append(_vertex_id(vertices, cache, x, y, z))
        rings.append(ring_vertices)

    first = rings[0]
    for index in range(angle_count):
        faces.append((top_center, first[index], first[(index + 1) % angle_count]))
    for ring_index in range(len(rings) - 1):
        inner = rings[ring_index]
        outer = rings[ring_index + 1]
        for index in range(angle_count):
            a = inner[index]
            b = inner[(index + 1) % angle_count]
            c = outer[(index + 1) % angle_count]
            d = outer[index]
            faces.extend(_quad_faces(a, d, c, b))
    if include_bottom:
        outer = rings[-1]
        for index in range(angle_count):
            faces.append((bottom_center, outer[(index + 1) % angle_count], outer[index]))

    return MeshPart(name, np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64), color).cleaned()


def _has_bad_mesh_edges(part: MeshPart) -> bool:
    part = part.cleaned()
    if part.is_empty():
        return True
    faces = np.asarray(part.faces, dtype=np.int64)
    if faces.size == 0:
        return True
    edges = np.vstack([
        faces[:, [0, 1]],
        faces[:, [1, 2]],
        faces[:, [2, 0]],
    ])
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool(np.any(counts != 2))


def _add_variable_roof_triangle(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    cache: VertexCache,
    coords: list[tuple[float, float]],
    z_base: float,
    top_z_at: Callable[[float, float], float],
    include_bottom: bool = True,
) -> None:
    if len(coords) < 3:
        return
    tri = coords[:3]
    area = _signed_area(tri + [tri[0]])
    if abs(area) <= 1e-12:
        return
    top_z = [max(z_base, top_z_at(x, y)) for x, y in tri]
    bottom_idx = [_vertex_id(vertices, cache, x, y, z_base) for x, y in tri]
    if include_bottom:
        if area >= 0:
            faces.append((bottom_idx[0], bottom_idx[2], bottom_idx[1]))
        else:
            faces.append((bottom_idx[0], bottom_idx[1], bottom_idx[2]))
    top_idx = [_vertex_id(vertices, cache, x, y, z) for (x, y), z in zip(tri, top_z)]
    if area >= 0:
        top_face = (top_idx[0], top_idx[1], top_idx[2])
    else:
        top_face = (top_idx[0], top_idx[2], top_idx[1])
    faces.append(top_face)


def _add_roof_exterior_sides(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    cache: VertexCache,
    poly: Polygon,
    shape: str,
    z_base: float,
    top_z_at: Callable[[float, float], float],
) -> None:
    exterior = _densify_ring_xy(poly.exterior.coords, _roof_exterior_step(poly, shape))
    if len(exterior) < 2:
        return

    for p0, p1 in zip(exterior, exterior[1:]):
        x0, y0 = float(p0[0]), float(p0[1])
        x1, y1 = float(p1[0]), float(p1[1])
        z0 = max(z_base, top_z_at(x0, y0))
        z1 = max(z_base, top_z_at(x1, y1))
        if max(z0, z1) - z_base <= 1e-5:
            continue
        top0 = _vertex_id(vertices, cache, x0, y0, z0)
        top1 = _vertex_id(vertices, cache, x1, y1, z1)
        bottom0 = _vertex_id(vertices, cache, x0, y0, z_base)
        bottom1 = _vertex_id(vertices, cache, x1, y1, z_base)
        top0_is_base = top0 == bottom0
        top1_is_base = top1 == bottom1
        if top0_is_base and top1_is_base:
            continue
        if top0_is_base:
            faces.append((top0, top1, bottom1))
        elif top1_is_base:
            faces.append((top0, top1, bottom0))
        else:
            faces.append((top0, top1, bottom1))
            faces.append((top0, bottom1, bottom0))


def build_osm_roof_mesh(
    poly: Polygon,
    z_base: float,
    z_top: float,
    shape: str,
    name: str,
    color: tuple[int, int, int, int],
    include_bottom: bool = True,
    tags: dict[str, str] | None = None,
) -> MeshPart:
    poly = _clean_polygon(poly)  # type: ignore[assignment]
    if poly is None or poly.interiors or z_top <= z_base + 0.05:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    if shape == "dome":
        dome = _build_dome_roof_mesh(poly, z_base, z_top, name, color, include_bottom)
        if not dome.is_empty():
            return dome
    if shape in {"gabled", "skillion", "hipped", "pyramidal"}:
        rectangular = _build_rectangular_roof_mesh(poly, z_base, z_top, shape, name, color, include_bottom, tags)
        if not rectangular.is_empty():
            return rectangular
    axes = _roof_axes(poly)
    points = _roof_sample_points(poly, shape, axes)
    if len(points) < 3:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    try:
        candidates = triangulate(MultiPoint(points))
    except Exception:
        candidates = []
    if not candidates:
        candidates = _triangulate_polygon(poly)
    top_z_at = _roof_top_z_function(poly, shape, z_base, z_top, tags)

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    cache: VertexCache = {}
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
                _add_variable_roof_triangle(
                    vertices,
                    faces,
                    cache,
                    coords,
                    z_base,
                    top_z_at,
                    include_bottom=include_bottom,
                )

    _add_roof_exterior_sides(vertices, faces, cache, poly, shape, z_base, top_z_at)
    if not faces:
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    return MeshPart(name, np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64), color).cleaned()


def extrude_building_with_osm_roof_on_terrain(
    poly: Polygon,
    terrain: TerrainGrid,
    height_mm: float,
    roof_height_mm: float,
    roof_shape: str,
    name: str,
    color: tuple[int, int, int, int],
    min_height_mm: float = 0.0,
    tags: dict[str, str] | None = None,
) -> MeshPart:
    roof_height_mm = max(0.05, min(float(roof_height_mm), max(0.05, height_mm * 0.85)))
    body_height_mm = max(0.05, height_mm - roof_height_mm)
    roof_base_z = _building_top_z_for_height(poly, terrain, body_height_mm, min_height_mm)
    roof_top_z = max(_building_top_z_for_height(poly, terrain, height_mm, min_height_mm), roof_base_z + 0.05)
    parts: list[MeshPart] = []
    has_body = body_height_mm > min_height_mm + 0.05
    if has_body:
        body = extrude_building_on_terrain(poly, terrain, body_height_mm, name, color, min_height_mm)
        if not body.is_empty():
            parts.append(body)
    roof = build_osm_roof_mesh(poly, roof_base_z, roof_top_z, roof_shape, name, color, include_bottom=True, tags=tags)
    if _has_bad_mesh_edges(roof):
        return extrude_building_on_terrain(poly, terrain, height_mm, name, color, min_height_mm)
    if not roof.is_empty():
        parts.append(roof)
    if not parts:
        return extrude_building_on_terrain(poly, terrain, height_mm, name, color, min_height_mm)
    return merge_parts(name, parts, color)


def _extrude_monument_on_terrain(
    poly: Polygon,
    terrain: TerrainGrid,
    height_mm: float,
    name: str,
    color: tuple[int, int, int, int],
    min_height_mm: float = 0.0,
) -> MeshPart:
    point = poly.representative_point()
    z0 = terrain.sample_z(point.x, point.y) + max(0.0, min_height_mm)
    height_mm = max(height_mm, 1.0)
    lower_base_top = z0 + max(0.18, height_mm * 0.08)
    upper_base_top = z0 + max(lower_base_top - z0 + 0.15, height_mm * 0.16)
    pedestal_top = z0 + max(upper_base_top - z0 + 0.15, height_mm * 0.26)
    shaft_top = z0 + max(pedestal_top - z0 + 0.25, height_mm * 0.93)
    top_z = z0 + height_mm

    layers: list[MeshPart] = [extrude_polygon(poly, z0, min(lower_base_top, top_z), name, color)]
    upper_base_poly = _scaled_building_poly(poly, 0.78)
    pedestal_poly = _oriented_rectangle_part(poly, 0.52, 0.46)
    shaft_poly = _oriented_rectangle_part(poly, 0.34, 0.24)
    cap_poly = _oriented_rectangle_part(poly, 0.26, 0.18)
    if upper_base_poly is not None and upper_base_top > lower_base_top + 0.05:
        layers.append(extrude_polygon(upper_base_poly, lower_base_top, min(upper_base_top, top_z), name, color))
    if pedestal_poly is not None and pedestal_top > upper_base_top + 0.05:
        layers.append(extrude_polygon(pedestal_poly, upper_base_top, min(pedestal_top, top_z), name, color))
    if shaft_poly is not None and shaft_top > pedestal_top + 0.05:
        layers.append(extrude_polygon(shaft_poly, pedestal_top, min(shaft_top, top_z), name, color))
    if cap_poly is not None and top_z > shaft_top + 0.05:
        layers.append(extrude_polygon(cap_poly, shaft_top, top_z, name, color))
    return merge_parts(name, layers, color)


def build_building_meshes(features: list[OSMFeature], scaler: ModelScaler, terrain: TerrainGrid, params: ModelParams) -> MeshPart:
    parts: list[MeshPart] = []
    tol_m = scaler.length_mm_to_m(params.simplify_tolerance_mm)
    high_detail = _is_high_detail_mode(params)
    for feature in _select_building_features_for_detail(features, params):
        if feature.tags.get("underground") == "yes" or feature.tags.get("location") == "underground":
            continue
        for poly_m in iter_polygons(feature.geometry_m):
            poly = transform_polygon_to_mm(poly_m, scaler, tol_m)
            if poly is None:
                continue
            h_m = parse_height_m(feature.tags, params)
            min_h_m = parse_min_height_m(feature.tags, params) if high_detail else 0.0
            if min_h_m >= h_m:
                h_m = min_h_m + max(1.0, params.level_height_m)
            h_mm = h_m * scaler.scale_mm_per_m * params.building_height_multiplier
            h_mm = float(np.clip(h_mm, params.min_building_height_mm, params.max_building_height_mm))
            min_h_mm = min_h_m * scaler.scale_mm_per_m * params.building_height_multiplier
            min_h_mm = float(max(0.0, min(min_h_mm, h_mm - 0.05)))
            roof_shape = _printable_roof_shape_from_tags(feature.tags) if high_detail else None
            roof_h_m = parse_roof_height_m(feature.tags, params, h_m) if roof_shape else None
            roof_h_mm = (
                roof_h_m * scaler.scale_mm_per_m * params.building_height_multiplier
                if roof_h_m is not None
                else h_mm * (0.42 if roof_shape == "dome" else 0.25)
            )
            roof_h_mm = float(max(0.08, min(roof_h_mm, max(0.08, h_mm * 0.85))))
            if high_detail and roof_shape:
                parts.append(extrude_building_with_osm_roof_on_terrain(
                    poly,
                    terrain,
                    h_mm,
                    roof_h_mm,
                    roof_shape,
                    "building",
                    COLORS["buildings"],
                    min_h_mm,
                    feature.tags,
                ))
            elif high_detail and _is_monument_feature(feature.tags):
                parts.append(_extrude_monument_on_terrain(poly, terrain, h_mm, "building", COLORS["buildings"], min_h_mm))
            else:
                parts.append(extrude_building_on_terrain(poly, terrain, h_mm, "building", COLORS["buildings"], min_h_mm))
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
    name: str = "road",
    color: tuple[int, int, int, int] = COLORS["roads"],
) -> MeshPart:
    x0, y0 = p0
    x1, y1 = p1
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length < max(0.10, width_mm * 0.15):
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)

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
    return MeshPart(name, vertices, faces, color).cleaned()


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


def build_route_meshes(
    route_lines_m: list[LineString],
    scaler: ModelScaler,
    terrain: TerrainGrid,
    params: ModelParams,
    water_union_m: BaseGeometry | None = None,
    *,
    width_mm: float | None = None,
    height_mm: float | None = None,
    offset_mm: float | None = None,
) -> MeshPart:
    parts: list[MeshPart] = []
    width_mm = params.route_width_mm if width_mm is None else width_mm
    thickness_mm = params.route_height_mm if height_mm is None else height_mm
    z_offset_mm = params.route_offset_mm if offset_mm is None else offset_mm
    for line_m in route_lines_m:
        coords_m = list(line_m.coords)
        if len(coords_m) < 2:
            continue
        if _terrain_has_relief(terrain):
            max_step_m = scaler.length_mm_to_m(_terrain_spacing_mm(terrain) * 1.2)
            coords_m = _densify_line_coords_m(coords_m, max(max_step_m, 1.0))
        coords_mm = [scaler.xy_to_mm(float(x), float(y)) for x, y in coords_m]
        for m0, m1, p0, p1 in zip(coords_m, coords_m[1:], coords_mm, coords_mm[1:]):
            segment_m = LineString([m0, m1])
            elevated = params.bridge_clearance_mm if (
                params.cut_out_water and _crosses_water_cutout(segment_m, water_union_m)
            ) else 0.0
            parts.append(_road_segment_part(
                p0,
                p1,
                width_mm,
                terrain,
                thickness_mm=thickness_mm,
                z_offset_mm=z_offset_mm,
                bridge_offset_mm=elevated,
                name="route",
                color=COLORS["route"],
            ))
    return merge_parts("route", parts, COLORS["route"])


def railway_width_m(tags: dict[str, str]) -> float:
    if "width" in tags:
        value = parse_length_m(tags["width"], min_m=0.5, max_m=40.0)
        if value is not None:
            return value
    railway = tags.get("railway", "")
    widths = {
        "rail": 5.0,
        "narrow_gauge": 3.2,
        "light_rail": 3.2,
        "tram": 2.6,
        "monorail": 3.0,
        "subway": 3.0,
    }
    return widths.get(railway, 3.0)


def rail_width_mm(tags: dict[str, str], scaler: ModelScaler, min_width_mm: float) -> float:
    return max(scaler.length_m_to_mm(railway_width_m(tags)), min_width_mm)


def build_rail_meshes(
    features: list[OSMFeature],
    scaler: ModelScaler,
    terrain: TerrainGrid,
    params: ModelParams,
    name: str,
    color: tuple[int, int, int, int],
    min_width_mm: float,
    thickness_mm: float,
    z_offset_mm: float,
    water_union_m: BaseGeometry | None = None,
) -> MeshPart:
    parts: list[MeshPart] = []
    tol_m = scaler.length_mm_to_m(max(params.simplify_tolerance_mm, 0.10))
    for feature in features:
        for line_m in iter_lines(feature.geometry_m):
            if tol_m > 0:
                line_m = line_m.simplify(tol_m, preserve_topology=False)
            coords_m = list(line_m.coords)
            if len(coords_m) < 2:
                continue
            if _terrain_has_relief(terrain):
                max_step_m = scaler.length_mm_to_m(_terrain_spacing_mm(terrain) * 1.2)
                coords_m = _densify_line_coords_m(coords_m, max(max_step_m, 1.0))
            coords_mm = [scaler.xy_to_mm(float(x), float(y)) for x, y in coords_m]
            width_mm = rail_width_mm(feature.tags, scaler, min_width_mm)
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
                    thickness_mm=thickness_mm,
                    z_offset_mm=z_offset_mm,
                    bridge_offset_mm=elevated,
                    name=name,
                    color=color,
                ))
    return merge_parts(name, parts, color)


def station_polygons_m(features: list[OSMFeature], scaler: ModelScaler, marker_radius_mm: float) -> list[Polygon]:
    polygons: list[Polygon] = []
    marker_radius_m = scaler.length_mm_to_m(max(marker_radius_mm, 0.30))
    for feature in features:
        feature_polys = list(iter_polygons(feature.geometry_m))
        if feature_polys:
            polygons.extend(feature_polys)
            continue
        for line in iter_lines(feature.geometry_m):
            try:
                polygons.extend(list(iter_polygons(line.buffer(marker_radius_m, cap_style=1, join_style=1))))
            except Exception:
                continue
        for point in iter_points(feature.geometry_m):
            try:
                polygons.extend(list(iter_polygons(point.buffer(marker_radius_m, quad_segs=8))))
            except Exception:
                continue
    return polygons


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


def water_union_geometry_m(
    water_features: list[OSMFeature],
    scaler: ModelScaler,
    params: ModelParams,
) -> BaseGeometry | None:
    water_polys = _feature_polygons(water_features) + _buffer_feature_lines(water_features, scaler, params, "water")
    return unary_union(water_polys) if water_polys else None


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


def _intersection_area(a: BaseGeometry | None, b: BaseGeometry) -> float:
    if a is None or a.is_empty or b.is_empty:
        return 0.0
    try:
        return float(a.intersection(b).area)
    except Exception:
        return 0.0


def _is_large_area_infill_parent(poly: Polygon, selection_area_m2: float) -> bool:
    if poly.area >= AREA_INFILL_PARENT_MIN_AREA_M2:
        return True
    if selection_area_m2 < AREA_INFILL_PARENT_LARGE_MAP_MIN_AREA_M2:
        return False
    return poly.area / selection_area_m2 >= AREA_INFILL_PARENT_MIN_SELECTION_FRACTION


def _area_infill_child_conflict(
    poly: Polygon,
    poly_index: int,
    area_polys: list[Polygon],
    area_tree: STRtree,
) -> tuple[int, float]:
    child_count = 0
    child_area = 0.0
    try:
        candidates = area_tree.query(poly)
    except Exception:
        return 0, 0.0
    for raw_index in candidates:
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if index == poly_index:
            continue
        child = area_polys[index]
        if child.is_empty or child.area <= 1e-6 or child.area >= poly.area * 0.65:
            continue
        try:
            overlap = float(poly.intersection(child).area)
        except Exception:
            continue
        if overlap <= 1e-6:
            continue
        if overlap / child.area >= 0.50:
            child_count += 1
            child_area += overlap
    return child_count, child_area


def _filter_large_parent_area_infill(
    area_polys: list[Polygon],
    scaler: ModelScaler,
    road_cutout_union: BaseGeometry | None,
    detail_union: BaseGeometry | None,
) -> list[Polygon]:
    if len(area_polys) < 2:
        return area_polys
    selection_area_m2 = scaler.length_mm_to_m(scaler.width_mm) * scaler.length_mm_to_m(scaler.height_mm)
    if selection_area_m2 <= 0:
        return area_polys
    area_tree = STRtree(area_polys)
    selected: list[Polygon] = []
    for index, poly in enumerate(area_polys):
        if poly.is_empty or poly.area <= 1e-6:
            continue
        if not _is_large_area_infill_parent(poly, selection_area_m2):
            selected.append(poly)
            continue
        area = float(poly.area)
        road_ratio = _intersection_area(road_cutout_union, poly) / area
        detail_ratio = _intersection_area(detail_union, poly) / area
        child_count, child_area = _area_infill_child_conflict(poly, index, area_polys, area_tree)
        child_ratio = child_area / area
        has_nested_detail = child_count >= AREA_INFILL_PARENT_CHILD_COUNT or child_ratio >= AREA_INFILL_PARENT_CHILD_RATIO
        covers_explicit_detail = detail_ratio >= AREA_INFILL_PARENT_DETAIL_RATIO
        covers_roads = road_ratio >= AREA_INFILL_PARENT_ROAD_RATIO
        if (covers_roads and (covers_explicit_detail or has_nested_detail)) or (covers_explicit_detail and has_nested_detail):
            continue
        selected.append(poly)
    return selected


def build_surface_layer_meshes(
    road_features: list[OSMFeature],
    water_features: list[OSMFeature],
    green_features: list[OSMFeature],
    parking_features: list[OSMFeature],
    airport_features: list[OSMFeature],
    area_infill_features: list[OSMFeature],
    building_features: list[OSMFeature],
    scaler: ModelScaler,
    terrain: TerrainGrid,
    params: ModelParams,
    rail_line_features: list[OSMFeature] | None = None,
    rail_station_features: list[OSMFeature] | None = None,
    subway_line_features: list[OSMFeature] | None = None,
    subway_station_features: list[OSMFeature] | None = None,
) -> list[MeshPart]:
    parts: list[MeshPart] = []
    rail_line_features = rail_line_features or []
    rail_station_features = rail_station_features or []
    subway_line_features = subway_line_features or []
    subway_station_features = subway_station_features or []

    road_area_polys = _feature_polygons(road_features)
    road_line_polys = _buffer_feature_lines(road_features, scaler, params, "road") if road_features else []
    water_polys = _feature_polygons(water_features) + _buffer_feature_lines(water_features, scaler, params, "water")
    green_polys = _feature_polygons(green_features)
    parking_polys = _feature_polygons(parking_features)
    airport_polys = _feature_polygons(airport_features) + _buffer_feature_lines(airport_features, scaler, params, "airport")
    area_infill_polys = _feature_polygons(area_infill_features)
    building_polys = _feature_polygons(building_features)

    water_union = unary_union(water_polys) if water_polys else None
    road_cutout_union = unary_union(road_area_polys + road_line_polys) if (road_area_polys or road_line_polys) else None
    green_union = unary_union(green_polys) if green_polys else None
    parking_union = unary_union(parking_polys) if parking_polys else None
    airport_union = unary_union(airport_polys) if airport_polys else None
    building_union = unary_union(building_polys) if building_polys else None
    detail_geoms = [
        geom
        for geom in (building_union, water_union, green_union, parking_union, airport_union, road_cutout_union)
        if geom is not None and not geom.is_empty
    ]
    detail_union = unary_union(detail_geoms) if detail_geoms else None

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
    if params.include_area_infill:
        selected_area_infill = list(area_infill_polys)
        if params.area_infill_mode == "empty_areas" and building_union is not None and not building_union.is_empty:
            selected_area_infill = [
                poly
                for poly in selected_area_infill
                if poly.intersection(building_union).area <= 1e-6
            ]
        elif params.area_infill_mode == "all_areas":
            selected_area_infill = _filter_large_parent_area_infill(
                selected_area_infill,
                scaler,
                road_cutout_union,
                detail_union,
            )
        parts.append(make_layer_mesh(
            "area_infill",
            selected_area_infill,
            scaler,
            terrain,
            params,
            thickness_mm=params.area_infill_height_mm,
            z_offset_mm=0.07,
            color=COLORS["area_infill"],
            simplify_tolerance_mm=surface_tol_mm,
        ))
    if params.include_green:
        parts.append(make_layer_mesh("green", cleaned_green, scaler, terrain, params, thickness_mm=0.25, z_offset_mm=0.05, color=COLORS["green"], simplify_tolerance_mm=surface_tol_mm))
    if params.include_parking:
        parts.append(make_layer_mesh("parking", cleaned_parking, scaler, terrain, params, thickness_mm=0.20, z_offset_mm=0.06, color=COLORS["parking"], simplify_tolerance_mm=surface_tol_mm))
    if params.include_airport:
        parts.append(make_layer_mesh("airport", cleaned_airport, scaler, terrain, params, thickness_mm=0.20, z_offset_mm=0.06, color=COLORS["airport"], simplify_tolerance_mm=surface_tol_mm))
    if params.include_water and not params.cut_out_water:
        parts.append(make_layer_mesh("water", list(iter_polygons(water_union)) if water_union else [], scaler, terrain, params, thickness_mm=0.35, z_offset_mm=0.08, color=COLORS["water"], simplify_tolerance_mm=surface_tol_mm))
    if params.include_roads:
        if road_area_polys:
            parts.append(make_layer_mesh(
                "roads",
                road_area_polys,
                scaler,
                terrain,
                params,
                thickness_mm=0.50,
                z_offset_mm=0.12,
                color=COLORS["roads"],
                simplify_tolerance_mm=surface_tol_mm,
            ))
        parts.append(build_road_meshes(road_features, scaler, terrain, params, water_union if params.cut_out_water else None))
    rail_water_union = water_union if params.cut_out_water else None
    if params.include_rail_lines:
        parts.append(build_rail_meshes(
            rail_line_features,
            scaler,
            terrain,
            params,
            name="rail_lines",
            color=COLORS["rail_lines"],
            min_width_mm=0.45,
            thickness_mm=0.36,
            z_offset_mm=0.18,
            water_union_m=rail_water_union,
        ))
    if params.include_subway_lines:
        parts.append(build_rail_meshes(
            subway_line_features,
            scaler,
            terrain,
            params,
            name="subway_lines",
            color=COLORS["subway_lines"],
            min_width_mm=0.38,
            thickness_mm=0.32,
            z_offset_mm=0.22,
            water_union_m=rail_water_union,
        ))
    if params.include_rail_stations:
        parts.append(make_layer_mesh(
            "rail_stations",
            station_polygons_m(rail_station_features, scaler, marker_radius_mm=1.15),
            scaler,
            terrain,
            params,
            thickness_mm=0.55,
            z_offset_mm=0.24,
            color=COLORS["rail_stations"],
            simplify_tolerance_mm=surface_tol_mm,
        ))
    if params.include_subway_stations:
        parts.append(make_layer_mesh(
            "subway_stations",
            station_polygons_m(subway_station_features, scaler, marker_radius_mm=0.95),
            scaler,
            terrain,
            params,
            thickness_mm=0.50,
            z_offset_mm=0.28,
            color=COLORS["subway_stations"],
            simplify_tolerance_mm=surface_tol_mm,
        ))

    return parts
