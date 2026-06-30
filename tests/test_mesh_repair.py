import numpy as np
from shapely.geometry import Polygon

from city_modeler.mesh_ops import extrude_polygon
from city_modeler.mesh_repair import mesh_diagnostics, repair_mesh_part, repair_mesh_parts
from city_modeler.mesh_types import MeshPart, merge_parts


def tetra_with_bad_faces() -> MeshPart:
    vertices = np.asarray([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    faces = np.asarray([
        [0, 2, 1],
        [0, 1, 3],
        [1, 2, 3],
        [2, 0, 3],
        [0, 2, 1],
        [0, 0, 1],
    ])
    return MeshPart("bad_tetra", vertices, faces, (255, 255, 255, 255))


def test_repair_mesh_part_removes_duplicate_and_degenerate_faces():
    repaired, report = repair_mesh_part(tetra_with_bad_faces())

    assert not repaired.is_empty()
    assert report["fixed"]["degenerate_faces_removed"] == 1
    assert report["fixed"]["duplicate_faces_removed"] >= 1
    assert report["before"]["non_manifold_edges"] > 0
    assert report["after"]["non_manifold_edges"] == 0
    assert report["after"]["watertight"] is True


def test_repair_mesh_parts_can_be_disabled():
    original = tetra_with_bad_faces()

    parts, report = repair_mesh_parts([original], enabled=False)

    assert parts[0] is original
    assert report["enabled"] is False
    assert report["status"] == "disabled"
    assert report["totals"]["non_manifold_edges"] > 0


def test_extruded_polygon_is_closed_before_repair():
    part = extrude_polygon(
        Polygon([(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]),
        0.0,
        1.0,
        "block",
        (255, 255, 255, 255),
    )

    diagnostics = mesh_diagnostics(part)

    assert diagnostics["watertight"] is True
    assert diagnostics["non_manifold_edges"] == 0


def test_repair_does_not_weld_adjacent_closed_bodies():
    left = extrude_polygon(
        Polygon([(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]),
        0.0,
        1.0,
        "left",
        (255, 255, 255, 255),
    )
    right = extrude_polygon(
        Polygon([(5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (5.0, 5.0)]),
        0.0,
        1.0,
        "right",
        (255, 255, 255, 255),
    )
    combined = merge_parts("adjacent", [left, right], (255, 255, 255, 255))

    repaired, report = repair_mesh_part(combined)
    diagnostics = mesh_diagnostics(repaired)

    assert report["fixed"]["merged_vertices"] is False
    assert diagnostics["watertight"] is True
    assert diagnostics["overused_edges"] == 0
    assert diagnostics["non_manifold_edges"] == 0


def test_extrusion_drops_unprintable_touching_holes():
    part = extrude_polygon(
        Polygon(
            [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
            holes=[[(5.0, 0.0), (5.01, 0.02), (4.99, 0.02), (5.0, 0.0)]],
        ),
        0.0,
        1.0,
        "water",
        (60, 140, 220, 255),
    )

    diagnostics = mesh_diagnostics(part)

    assert diagnostics["watertight"] is True
    assert diagnostics["non_manifold_edges"] == 0
