from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
import re

from .mesh_types import MeshPart

COLLADA_NS = "http://www.collada.org/2005/11/COLLADASchema"

ET.register_namespace("", COLLADA_NS)


def _tag(name: str) -> str:
    return f"{{{COLLADA_NS}}}{name}"


def _fmt(value: float) -> str:
    if abs(value) < 1e-9:
        value = 0.0
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def _safe_id(prefix: str, index: int, name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_.-")
    return f"{prefix}_{index}_{cleaned or 'part'}"


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in name).strip()
    return cleaned or "part"


def _color_text(color: tuple[int, int, int, int]) -> str:
    rgba = [max(0, min(255, int(channel))) / 255.0 for channel in color]
    return " ".join(_fmt(channel) for channel in rgba)


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_collada_xml(
    parts: list[MeshPart],
    *,
    title: str = "TopoTile Studio / 3D地图工坊 City Tile",
    creator: str = "TopoTile Studio / 3D地图工坊",
) -> bytes:
    cleaned_parts = [part.cleaned() for part in parts]
    non_empty = [part for part in cleaned_parts if not part.is_empty()]
    if not non_empty:
        raise ValueError("No mesh parts to write into DAE.")

    root = ET.Element(_tag("COLLADA"), {"version": "1.4.1"})
    asset = ET.SubElement(root, _tag("asset"))
    contributor = ET.SubElement(asset, _tag("contributor"))
    ET.SubElement(contributor, _tag("authoring_tool")).text = creator
    now = _timestamp()
    ET.SubElement(asset, _tag("created")).text = now
    ET.SubElement(asset, _tag("modified")).text = now
    ET.SubElement(asset, _tag("unit"), {"name": "millimeter", "meter": "0.001"})
    ET.SubElement(asset, _tag("up_axis")).text = "Z_UP"

    library_effects = ET.SubElement(root, _tag("library_effects"))
    library_materials = ET.SubElement(root, _tag("library_materials"))
    library_geometries = ET.SubElement(root, _tag("library_geometries"))
    library_scenes = ET.SubElement(root, _tag("library_visual_scenes"))
    scene = ET.SubElement(library_scenes, _tag("visual_scene"), {"id": "Scene", "name": title})

    for index, part in enumerate(non_empty, start=1):
        part_name = _safe_name(part.name)
        material_id = _safe_id("material", index, part.name)
        effect_id = f"{material_id}_effect"
        geometry_id = _safe_id("geometry", index, part.name)
        positions_id = f"{geometry_id}_positions"
        positions_array_id = f"{positions_id}_array"
        vertices_id = f"{geometry_id}_vertices"

        effect = ET.SubElement(library_effects, _tag("effect"), {"id": effect_id})
        profile = ET.SubElement(effect, _tag("profile_COMMON"))
        technique = ET.SubElement(profile, _tag("technique"), {"sid": "common"})
        lambert = ET.SubElement(technique, _tag("lambert"))
        diffuse = ET.SubElement(lambert, _tag("diffuse"))
        ET.SubElement(diffuse, _tag("color")).text = _color_text(part.color)

        material = ET.SubElement(library_materials, _tag("material"), {"id": material_id, "name": part_name})
        ET.SubElement(material, _tag("instance_effect"), {"url": f"#{effect_id}"})

        geometry = ET.SubElement(library_geometries, _tag("geometry"), {"id": geometry_id, "name": part_name})
        mesh = ET.SubElement(geometry, _tag("mesh"))
        source = ET.SubElement(mesh, _tag("source"), {"id": positions_id})
        values = " ".join(_fmt(float(value)) for vertex in part.vertices for value in vertex)
        ET.SubElement(source, _tag("float_array"), {
            "id": positions_array_id,
            "count": str(int(part.vertices.size)),
        }).text = values
        technique_common = ET.SubElement(source, _tag("technique_common"))
        accessor = ET.SubElement(technique_common, _tag("accessor"), {
            "source": f"#{positions_array_id}",
            "count": str(int(len(part.vertices))),
            "stride": "3",
        })
        for axis in ("X", "Y", "Z"):
            ET.SubElement(accessor, _tag("param"), {"name": axis, "type": "float"})

        vertices = ET.SubElement(mesh, _tag("vertices"), {"id": vertices_id})
        ET.SubElement(vertices, _tag("input"), {"semantic": "POSITION", "source": f"#{positions_id}"})

        triangles = ET.SubElement(mesh, _tag("triangles"), {
            "count": str(int(len(part.faces))),
            "material": material_id,
        })
        ET.SubElement(triangles, _tag("input"), {"semantic": "VERTEX", "source": f"#{vertices_id}", "offset": "0"})
        triangles.text = None
        ET.SubElement(triangles, _tag("p")).text = " ".join(str(int(value)) for face in part.faces for value in face)

        node = ET.SubElement(scene, _tag("node"), {"id": _safe_id("node", index, part.name), "name": part_name, "type": "NODE"})
        instance_geometry = ET.SubElement(node, _tag("instance_geometry"), {"url": f"#{geometry_id}"})
        bind_material = ET.SubElement(instance_geometry, _tag("bind_material"))
        material_common = ET.SubElement(bind_material, _tag("technique_common"))
        ET.SubElement(material_common, _tag("instance_material"), {"symbol": material_id, "target": f"#{material_id}"})

    scene_ref = ET.SubElement(root, _tag("scene"))
    ET.SubElement(scene_ref, _tag("instance_visual_scene"), {"url": "#Scene"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_dae(
    parts: list[MeshPart],
    path: str | Path,
    *,
    title: str = "TopoTile Studio / 3D地图工坊 City Tile",
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_collada_xml(parts, title=title))
    return path
