from __future__ import annotations

from pathlib import Path
import numpy as np
import trimesh

from .mesh_types import MeshPart


def write_glb(parts: list[MeshPart], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene = trimesh.Scene()
    added = 0
    for part in parts:
        part = part.cleaned()
        if part.is_empty():
            continue
        mesh = trimesh.Trimesh(vertices=part.vertices, faces=part.faces, process=False)
        color = np.array(part.color, dtype=np.uint8)
        mesh.visual.face_colors = np.tile(color, (len(mesh.faces), 1))
        scene.add_geometry(mesh, geom_name=part.name, node_name=part.name)
        added += 1
    if added == 0:
        raise ValueError("No mesh parts to write into GLB.")
    data = scene.export(file_type="glb")
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    return path
