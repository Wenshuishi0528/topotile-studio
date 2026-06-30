import numpy as np

from city_modeler.mesh_repair import repair_mesh_part, repair_mesh_parts
from city_modeler.mesh_types import MeshPart


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
