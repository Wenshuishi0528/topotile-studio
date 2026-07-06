from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

ROAD_LEVELS = [
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "pedestrian",
    "track",
    "cycleway",
    "footway",
    "path",
    "steps",
]
SELECTION_SHAPES = ["rectangle", "circle", "hexagon"]
AREA_INFILL_MODES = ["empty_areas", "all_areas"]
MODEL_DETAIL_MODES = ["normal", "high"]
MODEL_DATA_SOURCES = ["osm", "local_vector"]
VECTOR_COORDINATE_SYSTEMS = ["wgs84", "gcj02", "bd09"]
DEFAULT_ROAD_LEVELS = [
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "pedestrian",
    "footway",
]


def normalize_route_segments(value: object, max_points: int = 60000) -> list[list[list[float]]]:
    if not isinstance(value, list):
        return []
    segments: list[list[list[float]]] = []
    point_count = 0
    for raw_segment in value:
        if not isinstance(raw_segment, list):
            continue
        segment: list[list[float]] = []
        previous: tuple[int, int] | None = None
        for raw_point in raw_segment:
            if not isinstance(raw_point, (list, tuple)) or len(raw_point) < 2:
                continue
            try:
                lat = float(raw_point[0])
                lon = float(raw_point[1])
            except (TypeError, ValueError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            key = (int(round(lat * 1_000_000)), int(round(lon * 1_000_000)))
            if key == previous:
                continue
            previous = key
            segment.append([lat, lon])
            point_count += 1
            if point_count >= max_points:
                break
        if len(segment) >= 2:
            segments.append(segment)
        if point_count >= max_points:
            break
    return segments


def _route_float(value: object, default: float, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, min_value), max_value)


def _route_name(value: object, default: str) -> str:
    name = str(value or "").strip()
    name = " ".join(name.split())
    return (name[:80] or default)


def normalize_route_configs(
    value: object,
    *,
    fallback_name: str = "",
    fallback_segments: object | None = None,
    fallback_width: float = 1.20,
    fallback_height: float = 0.80,
    fallback_offset: float = 0.15,
    max_routes: int = 12,
    max_points: int = 60000,
) -> list[dict[str, Any]]:
    raw_routes = value if isinstance(value, list) else []
    if not raw_routes and fallback_segments:
        raw_routes = [{
            "name": fallback_name,
            "segments": fallback_segments,
            "width_mm": fallback_width,
            "height_mm": fallback_height,
            "offset_mm": fallback_offset,
        }]

    routes: list[dict[str, Any]] = []
    point_count = 0
    for idx, raw_route in enumerate(raw_routes[:max_routes]):
        if not isinstance(raw_route, dict):
            continue
        remaining_points = max(max_points - point_count, 0)
        if remaining_points <= 0:
            break
        segments = normalize_route_segments(
            raw_route.get("segments", raw_route.get("route_segments", [])),
            max_points=remaining_points,
        )
        if not segments:
            continue
        point_count += sum(len(segment) for segment in segments)
        name = _route_name(
            raw_route.get("name", raw_route.get("route_name", raw_route.get("filename", ""))),
            f"Route #{idx + 1}",
        )
        routes.append({
            "name": name,
            "segments": segments,
            "width_mm": _route_float(
                raw_route.get("width_mm", raw_route.get("route_width_mm", fallback_width)),
                fallback_width,
                0.15,
                20.0,
            ),
            "height_mm": _route_float(
                raw_route.get("height_mm", raw_route.get("route_height_mm", fallback_height)),
                fallback_height,
                0.05,
                20.0,
            ),
            "offset_mm": _route_float(
                raw_route.get("offset_mm", raw_route.get("route_offset_mm", fallback_offset)),
                fallback_offset,
                0.0,
                30.0,
            ),
        })
        if point_count >= max_points:
            break
    return routes


def safe_output_stem(value: object, default: str = "city_model") -> str:
    stem = str(value or "").strip()
    for suffix in (".3mf", ".glb", ".dae", ".stl", ".zip"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    cleaned = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in stem)
    cleaned = "_".join(cleaned.split()).strip("._-")
    return (cleaned[:80] or default)


@dataclass(slots=True)
class ModelParams:
    south: float
    west: float
    north: float
    east: float

    max_size_mm: float = 180.0
    base_thickness_mm: float = 3.0
    vertical_exaggeration: float = 2.0
    building_height_multiplier: float = 1.0
    default_building_height_m: float = 9.0
    level_height_m: float = 3.0
    min_building_height_mm: float = 1.2
    max_building_height_mm: float = 45.0
    min_road_width_mm: float = 0.8
    footway_width_mm: float = 0.60
    pedestrian_width_mm: float = 0.60
    bridge_clearance_mm: float = 2.5
    area_infill_height_mm: float = 0.60
    route_width_mm: float = 1.20
    route_height_mm: float = 0.80
    route_offset_mm: float = 0.15
    terrain_grid_size: int = 96
    max_terrain_height_mm: float = 35.0
    simplify_tolerance_mm: float = 0.15
    auto_terrain: bool = False
    large_map_mode: bool = False
    terrain_tile_zoom: int = 13
    osm_tile_size_km: float = 2.0
    cut_out_water: bool = False
    selection_shape: str = "rectangle"
    road_cleaning_level: int = 1
    chunk_export: bool = False
    chunk_rows: int = 1
    chunk_cols: int = 1
    auto_repair_mesh: bool = True
    export_print_color_groups: bool = True
    enable_render_textures: bool = False
    texture_wall_repeat_mm: float = 12.0
    texture_roof_repeat_mm: float = 18.0
    include_landmark_replacement: bool = False
    landmark_scale: float = 1.0
    landmark_rotation_deg: float = 0.0
    landmark_z_offset_mm: float = 0.0
    landmark_fit_to_footprint: bool = True
    landmark_replace_original: bool = True

    include_buildings: bool = True
    include_roads: bool = True
    include_water: bool = True
    include_green: bool = True
    include_parking: bool = True
    include_airport: bool = True
    include_area_infill: bool = True
    include_route: bool = False
    include_rail_lines: bool = False
    include_rail_stations: bool = False
    include_subway_lines: bool = False
    include_subway_stations: bool = False
    include_power_line_layers: bool = False
    include_power_lines: bool = True
    include_minor_power_lines: bool = True
    include_power_towers: bool = True
    include_power_plants: bool = False

    osm_overpass_url: str = "https://overpass-api.de/api/interpreter"
    road_levels: list[str] = field(default_factory=lambda: list(DEFAULT_ROAD_LEVELS))
    dem_attribution: str = ""
    project_name: str = "TopoTile Studio / 3D地图工坊 City Tile"
    output_name: str = "city_model"
    model_data_source: str = "osm"
    vector_coordinate_system: str = "wgs84"
    vector_data_attribution: str = ""
    area_infill_mode: str = "empty_areas"
    model_detail_mode: str = "normal"
    landmark_osm_id: str = ""
    route_name: str = ""
    route_segments: list[list[list[float]]] = field(default_factory=list)
    routes: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelParams":
        bbox = data.get("bbox")
        if bbox and len(bbox) == 4:
            south, west, north, east = map(float, bbox)
        else:
            south = float(data["south"])
            west = float(data["west"])
            north = float(data["north"])
            east = float(data["east"])

        values = dict(data)
        values.pop("bbox", None)
        if "export_print_color_groups" not in values and "random_export_colors" in values:
            values["export_print_color_groups"] = values["random_export_colors"]
        values.update({"south": south, "west": west, "north": north, "east": east})

        valid = {field.name for field in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in values.items() if k in valid}

        numeric_fields = {
            "south", "west", "north", "east", "max_size_mm", "base_thickness_mm",
            "vertical_exaggeration", "building_height_multiplier", "default_building_height_m",
            "level_height_m", "min_building_height_mm", "max_building_height_mm",
            "min_road_width_mm", "footway_width_mm", "pedestrian_width_mm", "bridge_clearance_mm",
            "area_infill_height_mm", "route_width_mm", "route_height_mm", "route_offset_mm",
            "max_terrain_height_mm", "simplify_tolerance_mm",
            "osm_tile_size_km", "texture_wall_repeat_mm", "texture_roof_repeat_mm",
            "landmark_scale", "landmark_rotation_deg", "landmark_z_offset_mm",
        }
        int_fields = {"terrain_grid_size", "terrain_tile_zoom", "road_cleaning_level", "chunk_rows", "chunk_cols"}
        bool_fields = {
            "auto_terrain", "large_map_mode", "cut_out_water", "chunk_export", "auto_repair_mesh",
            "export_print_color_groups", "enable_render_textures",
            "include_landmark_replacement", "landmark_fit_to_footprint", "landmark_replace_original",
            "include_buildings", "include_roads", "include_water", "include_green", "include_parking",
            "include_airport", "include_area_infill", "include_route",
            "include_rail_lines", "include_rail_stations", "include_subway_lines", "include_subway_stations",
            "include_power_line_layers", "include_power_lines", "include_minor_power_lines",
            "include_power_towers", "include_power_plants",
        }

        for key in numeric_fields & filtered.keys():
            filtered[key] = float(filtered[key])
        for key in int_fields & filtered.keys():
            filtered[key] = int(filtered[key])
        for key in bool_fields & filtered.keys():
            value = filtered[key]
            if isinstance(value, str):
                filtered[key] = value.lower() in {"1", "true", "yes", "on"}
            else:
                filtered[key] = bool(value)
        if "selection_shape" in filtered:
            filtered["selection_shape"] = str(filtered["selection_shape"]).strip().lower()
        if "area_infill_mode" in filtered:
            filtered["area_infill_mode"] = str(filtered["area_infill_mode"]).strip().lower()
        if "model_detail_mode" in filtered:
            filtered["model_detail_mode"] = str(filtered["model_detail_mode"]).strip().lower()
        if "model_data_source" in filtered:
            filtered["model_data_source"] = str(filtered["model_data_source"]).strip().lower()
        if "vector_coordinate_system" in filtered:
            filtered["vector_coordinate_system"] = str(filtered["vector_coordinate_system"]).strip().lower()
        if "road_levels" in filtered:
            value = filtered["road_levels"]
            if isinstance(value, str):
                levels = [v.strip() for v in value.split(",") if v.strip()]
            else:
                levels = [str(v) for v in value]
            supported = set(ROAD_LEVELS)
            filtered["road_levels"] = [level for level in levels if level in supported]
        if "route_segments" in filtered:
            filtered["route_segments"] = normalize_route_segments(filtered["route_segments"])
        if "routes" in filtered:
            filtered["routes"] = normalize_route_configs(
                filtered["routes"],
                fallback_width=float(filtered.get("route_width_mm", 1.20)),
                fallback_height=float(filtered.get("route_height_mm", 0.80)),
                fallback_offset=float(filtered.get("route_offset_mm", 0.15)),
            )

        obj = cls(**filtered)
        if not obj.include_power_line_layers:
            obj.include_power_lines = False
            obj.include_minor_power_lines = False
            obj.include_power_towers = False
        obj.validate()
        return obj

    def validate(self) -> None:
        if not (-90 <= self.south < self.north <= 90):
            raise ValueError("Invalid latitude bounds. Expected south < north within [-90, 90].")
        if not (-180 <= self.west < self.east <= 180):
            raise ValueError("Invalid longitude bounds. Expected west < east within [-180, 180].")
        if self.max_size_mm <= 0 or self.max_size_mm > 240:
            raise ValueError("max_size_mm must be in the range (0, 240].")
        if self.base_thickness_mm < 0.8:
            raise ValueError("base_thickness_mm should be at least 0.8 mm for printing.")
        if self.terrain_grid_size < 2 or self.terrain_grid_size > 220:
            raise ValueError("terrain_grid_size must be between 2 and 220.")
        if self.terrain_tile_zoom < 8 or self.terrain_tile_zoom > 14:
            raise ValueError("terrain_tile_zoom must be between 8 and 14.")
        if self.osm_tile_size_km < 0.5 or self.osm_tile_size_km > 20:
            raise ValueError("osm_tile_size_km must be between 0.5 and 20.")
        if self.footway_width_mm < 0.15 or self.footway_width_mm > 10:
            raise ValueError("footway_width_mm must be between 0.15 and 10.")
        if self.pedestrian_width_mm < 0.15 or self.pedestrian_width_mm > 10:
            raise ValueError("pedestrian_width_mm must be between 0.15 and 10.")
        if self.bridge_clearance_mm < 0 or self.bridge_clearance_mm > 30:
            raise ValueError("bridge_clearance_mm must be between 0 and 30.")
        if self.area_infill_height_mm < 0.05 or self.area_infill_height_mm > 10:
            raise ValueError("area_infill_height_mm must be between 0.05 and 10.")
        if self.route_width_mm < 0.15 or self.route_width_mm > 20:
            raise ValueError("route_width_mm must be between 0.15 and 20.")
        if self.route_height_mm < 0.05 or self.route_height_mm > 20:
            raise ValueError("route_height_mm must be between 0.05 and 20.")
        if self.route_offset_mm < 0 or self.route_offset_mm > 30:
            raise ValueError("route_offset_mm must be between 0 and 30.")
        if self.selection_shape not in SELECTION_SHAPES:
            raise ValueError(f"selection_shape must be one of: {', '.join(SELECTION_SHAPES)}")
        if self.area_infill_mode not in AREA_INFILL_MODES:
            raise ValueError(f"area_infill_mode must be one of: {', '.join(AREA_INFILL_MODES)}")
        if self.model_detail_mode not in MODEL_DETAIL_MODES:
            raise ValueError(f"model_detail_mode must be one of: {', '.join(MODEL_DETAIL_MODES)}")
        if self.model_data_source not in MODEL_DATA_SOURCES:
            raise ValueError(f"model_data_source must be one of: {', '.join(MODEL_DATA_SOURCES)}")
        if self.vector_coordinate_system not in VECTOR_COORDINATE_SYSTEMS:
            raise ValueError(f"vector_coordinate_system must be one of: {', '.join(VECTOR_COORDINATE_SYSTEMS)}")
        if self.road_cleaning_level < 0 or self.road_cleaning_level > 3:
            raise ValueError("road_cleaning_level must be between 0 and 3.")
        if self.chunk_rows < 1 or self.chunk_rows > 6:
            raise ValueError("chunk_rows must be between 1 and 6.")
        if self.chunk_cols < 1 or self.chunk_cols > 6:
            raise ValueError("chunk_cols must be between 1 and 6.")
        if self.chunk_rows * self.chunk_cols > 24:
            raise ValueError("chunk export supports up to 24 pieces per job.")
        self.landmark_osm_id = str(self.landmark_osm_id or "").strip()
        if self.landmark_scale <= 0 or self.landmark_scale > 1000:
            raise ValueError("landmark_scale must be in the range (0, 1000].")
        if self.landmark_z_offset_mm < -200 or self.landmark_z_offset_mm > 200:
            raise ValueError("landmark_z_offset_mm must be between -200 and 200.")
        if not math.isfinite(self.landmark_rotation_deg):
            raise ValueError("landmark_rotation_deg must be a finite number.")
        if self.include_landmark_replacement and not self.landmark_osm_id:
            raise ValueError("include_landmark_replacement requires a target OSM ID.")
        self.output_name = safe_output_stem(self.output_name)
        unsupported = sorted(set(self.road_levels) - set(ROAD_LEVELS))
        if unsupported:
            raise ValueError(f"Unsupported road level(s): {', '.join(unsupported)}")
        self.route_segments = normalize_route_segments(self.route_segments)
        self.routes = normalize_route_configs(
            self.routes,
            fallback_name=self.route_name,
            fallback_segments=self.route_segments,
            fallback_width=self.route_width_mm,
            fallback_height=self.route_height_mm,
            fallback_offset=self.route_offset_mm,
        )
        if self.routes:
            first_route = self.routes[0]
            self.route_name = str(first_route["name"])
            self.route_segments = first_route["segments"]
            self.route_width_mm = float(first_route["width_mm"])
            self.route_height_mm = float(first_route["height_mm"])
            self.route_offset_mm = float(first_route["offset_mm"])
        if self.include_route and not self.routes:
            raise ValueError("include_route requires an uploaded GPX/KML route or saved route points.")

    @property
    def bbox_tuple(self) -> tuple[float, float, float, float]:
        return (self.south, self.west, self.north, self.east)
