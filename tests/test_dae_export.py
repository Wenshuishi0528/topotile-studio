from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

from city_modeler.export_dae import COLLADA_NS, write_dae
from city_modeler.mesh_types import MeshPart


def test_write_dae_creates_collada_mesh_with_material(tmp_path: Path):
    vertices = np.array([
        [0, 0, 0],
        [10, 0, 0],
        [0, 10, 0],
    ], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    part = MeshPart("buildings", vertices, faces, (255, 255, 255, 255))

    path = write_dae([part], tmp_path / "model.dae", title="SketchUp test")

    assert path.exists()
    root = ET.fromstring(path.read_bytes())
    ns = {"c": COLLADA_NS}
    assert root.tag == f"{{{COLLADA_NS}}}COLLADA"
    assert root.attrib["version"] == "1.4.1"
    assert root.find("c:asset/c:unit", ns).attrib == {"name": "millimeter", "meter": "0.001"}
    assert root.findtext("c:asset/c:up_axis", namespaces=ns) == "Z_UP"
    triangles = root.find(".//c:triangles", ns)
    assert triangles is not None
    assert triangles.attrib["count"] == "1"
    assert triangles.findtext("c:p", namespaces=ns) == "0 1 2"
    color = root.findtext(".//c:diffuse/c:color", namespaces=ns)
    assert color == "1 1 1 1"
