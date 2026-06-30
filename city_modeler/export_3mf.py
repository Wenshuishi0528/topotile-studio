from __future__ import annotations

from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
import trimesh

from .mesh_types import MeshPart

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
MODEL_REL_TYPE = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"

ET.register_namespace("", CORE_NS)


def _fmt(value: float) -> str:
    if abs(value) < 1e-9:
        value = 0.0
    return f"{value:.5f}".rstrip("0").rstrip(".") or "0"


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name).strip()
    return cleaned or "object"


def make_model_xml(parts: list[MeshPart], title: str = "TopoTile Studio City Tile", creator: str = "TopoTile Studio") -> bytes:
    model = ET.Element(f"{{{CORE_NS}}}model", {"unit": "millimeter", "xml:lang": "en-US"})
    ET.SubElement(model, f"{{{CORE_NS}}}metadata", {"name": "Title"}).text = title
    ET.SubElement(model, f"{{{CORE_NS}}}metadata", {"name": "Designer"}).text = creator
    ET.SubElement(model, f"{{{CORE_NS}}}metadata", {"name": "Description"}).text = "Generated from OpenStreetMap vector data and optional DEM terrain."

    resources = ET.SubElement(model, f"{{{CORE_NS}}}resources")
    build = ET.SubElement(model, f"{{{CORE_NS}}}build")

    object_id = 1
    for part in parts:
        part = part.cleaned()
        if part.is_empty():
            continue
        obj = ET.SubElement(resources, f"{{{CORE_NS}}}object", {
            "id": str(object_id),
            "type": "model",
            "name": _safe_name(part.name),
        })
        mesh = ET.SubElement(obj, f"{{{CORE_NS}}}mesh")
        vertices_el = ET.SubElement(mesh, f"{{{CORE_NS}}}vertices")
        for v in part.vertices:
            ET.SubElement(vertices_el, f"{{{CORE_NS}}}vertex", {
                "x": _fmt(float(v[0])),
                "y": _fmt(float(v[1])),
                "z": _fmt(float(v[2])),
            })
        triangles_el = ET.SubElement(mesh, f"{{{CORE_NS}}}triangles")
        for f in part.faces:
            ET.SubElement(triangles_el, f"{{{CORE_NS}}}triangle", {
                "v1": str(int(f[0])),
                "v2": str(int(f[1])),
                "v3": str(int(f[2])),
            })
        ET.SubElement(build, f"{{{CORE_NS}}}item", {"objectid": str(object_id)})
        object_id += 1

    return ET.tostring(model, encoding="utf-8", xml_declaration=True)


def make_rels_xml() -> bytes:
    relationships = ET.Element(f"{{{RELS_NS}}}Relationships")
    ET.SubElement(relationships, f"{{{RELS_NS}}}Relationship", {
        "Target": "/3D/3dmodel.model",
        "Id": "rel0",
        "Type": MODEL_REL_TYPE,
    })
    return ET.tostring(relationships, encoding="utf-8", xml_declaration=True)


def make_content_types_xml() -> bytes:
    types = ET.Element(f"{{{CT_NS}}}Types")
    ET.SubElement(types, f"{{{CT_NS}}}Default", {
        "Extension": "rels",
        "ContentType": "application/vnd.openxmlformats-package.relationships+xml",
    })
    ET.SubElement(types, f"{{{CT_NS}}}Default", {
        "Extension": "model",
        "ContentType": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
    })
    return ET.tostring(types, encoding="utf-8", xml_declaration=True)


def write_3mf(parts: list[MeshPart], path: str | Path, title: str = "TopoTile Studio City Tile") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    non_empty = [part.cleaned() for part in parts if not part.cleaned().is_empty()]
    if not non_empty:
        raise ValueError("No mesh parts to write into 3MF.")
    scene = trimesh.Scene()
    for index, part in enumerate(non_empty, start=1):
        mesh = trimesh.Trimesh(vertices=part.vertices, faces=part.faces, process=False)
        color = np.array(part.color, dtype=np.uint8)
        mesh.visual.face_colors = np.tile(color, (len(mesh.faces), 1))
        name = _safe_name(part.name) or f"object_{index}"
        scene.add_geometry(mesh, geom_name=name, node_name=name)

    data = scene.export(file_type="3mf")
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    return path


def validate_3mf(path: str | Path) -> dict[str, int | list[str]]:
    path = Path(path)
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        required = {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"}
        missing = sorted(required - set(names))
        if missing:
            raise ValueError(f"3MF is missing required files: {missing}")
        xml = zf.read("3D/3dmodel.model")
    root = ET.fromstring(xml)
    ns = {"m": CORE_NS}
    vertices = root.findall(".//m:vertex", ns)
    triangles = root.findall(".//m:triangle", ns)
    objects = root.findall(".//m:object", ns)
    return {"objects": len(objects), "vertices": len(vertices), "triangles": len(triangles), "files": names}
