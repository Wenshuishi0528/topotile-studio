import numpy as np

from city_modeler.mesh_types import MeshPart
from city_modeler.params import ModelParams
from city_modeler.pipeline import export_parts_with_print_color_groups


def _part(name: str, color: tuple[int, int, int, int]) -> MeshPart:
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=float,
    )
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)
    return MeshPart(name, vertices, faces, color)


def test_print_color_groups_apply_stable_3mf_layer_colors():
    params = ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, export_print_color_groups=True)
    terrain = _part("terrain", (198, 188, 160, 255))
    buildings = _part("buildings", (230, 230, 225, 255))
    parking = _part("parking", (168, 168, 156, 255))
    area_infill = _part("area_infill", (176, 164, 138, 255))
    roads = _part("roads", (120, 120, 120, 255))
    water = _part("water", (60, 140, 220, 255))
    green = _part("green", (80, 160, 90, 255))
    rail_lines = _part("rail_lines", (72, 72, 72, 255))
    rail_stations = _part("rail_stations", (214, 214, 206, 255))
    subway_lines = _part("subway_lines", (170, 55, 170, 255))
    subway_stations = _part("subway_stations", (205, 180, 230, 255))

    export_parts, summary = export_parts_with_print_color_groups(
        [
            terrain,
            buildings,
            parking,
            area_infill,
            roads,
            water,
            green,
            rail_lines,
            rail_stations,
            subway_lines,
            subway_stations,
        ],
        params,
    )

    assert summary["enabled"] is True
    assert summary["mode"] == "stable_layer_groups"
    assert summary["target"] == "3mf"
    assert export_parts[0] is terrain
    assert export_parts[1].color == (245, 245, 245, 255)
    assert export_parts[2].color == (245, 245, 245, 255)
    assert export_parts[3].color == (245, 245, 245, 255)
    assert export_parts[4].color == (115, 115, 115, 255)
    assert export_parts[5].color == (35, 125, 235, 255)
    assert export_parts[6].color == (30, 170, 75, 255)
    assert export_parts[7].color == (75, 75, 75, 255)
    assert export_parts[8].color == (245, 245, 245, 255)
    assert export_parts[9].color == (170, 55, 170, 255)
    assert export_parts[10].color == (245, 245, 245, 255)
    assert export_parts[1].vertices is buildings.vertices
    assert {item["name"] for item in summary["parts"]} == {
        "buildings",
        "parking",
        "area_infill",
        "roads",
        "water",
        "green",
        "rail_lines",
        "rail_stations",
        "subway_lines",
        "subway_stations",
    }


def test_print_color_groups_disabled_returns_original_parts():
    params = ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, export_print_color_groups=False)
    buildings = _part("buildings", (230, 230, 225, 255))

    export_parts, summary = export_parts_with_print_color_groups([buildings], params)

    assert summary == {"enabled": False}
    assert export_parts is not None
    assert export_parts[0] is buildings
