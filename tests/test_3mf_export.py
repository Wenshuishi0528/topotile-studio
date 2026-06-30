from pathlib import Path
import zipfile
import numpy as np
import trimesh

from city_modeler.mesh_types import MeshPart
from city_modeler.export_3mf import write_3mf, validate_3mf


def test_write_basic_3mf(tmp_path: Path):
    vertices = np.array([
        [0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]
    ], dtype=float)
    faces = np.array([
        [0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]
    ], dtype=np.int64)
    part = MeshPart("tetra", vertices, faces)
    path = write_3mf([part], tmp_path / "test.3mf")
    info = validate_3mf(path)
    assert info["objects"] == 1
    assert info["vertices"] == 4
    assert info["triangles"] == 4


def test_write_3mf_is_reimportable_by_trimesh(tmp_path: Path):
    vertices = np.array([
        [0, 0, 0], [20, 0, 0], [0, 20, 0], [0, 0, 20]
    ], dtype=float)
    faces = np.array([
        [0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]
    ], dtype=np.int64)
    path = write_3mf([MeshPart("tetra", vertices, faces)], tmp_path / "test.3mf")

    scene = trimesh.load(path)
    assert len(scene.geometry) == 1
    assert sum(len(mesh.faces) for mesh in scene.geometry.values()) == 4

    with zipfile.ZipFile(path, "r") as zf:
        model_xml = zf.read("3D/3dmodel.model").decode("utf-8")
        rels_xml = zf.read("_rels/.rels").decode("utf-8")
    assert "p:UUID" in model_xml
    assert "<Relationships xmlns=" in rels_xml
