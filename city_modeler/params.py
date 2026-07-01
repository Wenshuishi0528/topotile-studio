from __future__ import annotations

from dataclasses import dataclass, field
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


def safe_output_stem(value: object, default: str = "city_model") -> str:
    stem = str(value or "").strip()
    for suffix in (".3mf", ".glb", ".stl", ".zip"):
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

    include_buildings: bool = True
    include_roads: bool = True
    include_water: bool = True
    include_green: bool = True
    include_parking: bool = True
    include_airport: bool = True
    include_area_infill: bool = True
    include_route: bool = False

    osm_overpass_url: str = "https://overpass-api.de/api/interpreter"
    road_levels: list[str] = field(default_factory=lambda: list(DEFAULT_ROAD_LEVELS))
    dem_attribution: str = ""
    project_name: str = "TopoTile Studio City Tile"
    output_name: str = "city_model"
    area_infill_mode: str = "empty_areas"
    route_name: str = ""
    route_segments: list[list[list[float]]] = field(default_factory=list)

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
            "osm_tile_size_km",
        }
        int_fields = {"terrain_grid_size", "terrain_tile_zoom", "road_cleaning_level", "chunk_rows", "chunk_cols"}
        bool_fields = {
            "auto_terrain", "large_map_mode", "cut_out_water", "chunk_export", "auto_repair_mesh",
            "include_buildings", "include_roads", "include_water", "include_green", "include_parking",
            "include_airport", "include_area_infill", "include_route"
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

        obj = cls(**filtered)
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
        if self.road_cleaning_level < 0 or self.road_cleaning_level > 3:
            raise ValueError("road_cleaning_level must be between 0 and 3.")
        if self.chunk_rows < 1 or self.chunk_rows > 6:
            raise ValueError("chunk_rows must be between 1 and 6.")
        if self.chunk_cols < 1 or self.chunk_cols > 6:
            raise ValueError("chunk_cols must be between 1 and 6.")
        if self.chunk_rows * self.chunk_cols > 24:
            raise ValueError("chunk export supports up to 24 pieces per job.")
        self.output_name = safe_output_stem(self.output_name)
        unsupported = sorted(set(self.road_levels) - set(ROAD_LEVELS))
        if unsupported:
            raise ValueError(f"Unsupported road level(s): {', '.join(unsupported)}")
        self.route_segments = normalize_route_segments(self.route_segments)
        if self.include_route and not self.route_segments:
            raise ValueError("include_route requires an uploaded GPX/KML route or saved route points.")

    @property
    def bbox_tuple(self) -> tuple[float, float, float, float]:
        return (self.south, self.west, self.north, self.east)
