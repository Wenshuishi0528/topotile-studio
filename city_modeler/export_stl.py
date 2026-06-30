from __future__ import annotations

from pathlib import Path
import numpy as np
import trimesh

from .mesh_types import MeshPart


def write_stl(parts: list[MeshPart], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    vertices_list: list[np.ndarray] = []
    faces_list: list[np.ndarray] = []
    offset = 0
    for part in parts:
        part = part.cleaned()
        if part.is_empty():
            continue
        vertices_list.append(part.vertices)
        faces_list.append(part.faces + offset)
        offset += len(part.vertices)
    if not vertices_list:
        raise ValueError("No mesh parts to write into STL.")
    mesh = trimesh.Trimesh(vertices=np.vstack(vertices_list), faces=np.vstack(faces_list), process=False)
    mesh.export(path, file_type="stl")
    return path
