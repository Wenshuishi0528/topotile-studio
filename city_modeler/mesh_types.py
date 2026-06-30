from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import numpy as np


@dataclass(slots=True)
class MeshPart:
    name: str
    vertices: np.ndarray
    faces: np.ndarray
    color: tuple[int, int, int, int] = (200, 200, 200, 255)

    def is_empty(self) -> bool:
        return self.vertices.size == 0 or self.faces.size == 0

    def cleaned(self) -> "MeshPart":
        vertices = np.asarray(self.vertices, dtype=float)
        faces = np.asarray(self.faces, dtype=np.int64)
        if vertices.ndim != 2 or vertices.shape[1] != 3:
            raise ValueError(f"MeshPart {self.name} has invalid vertices shape {vertices.shape}")
        if faces.ndim != 2 or faces.shape[1] != 3:
            raise ValueError(f"MeshPart {self.name} has invalid faces shape {faces.shape}")
        mask = np.all(np.isfinite(vertices), axis=1)
        if not mask.all():
            remap = np.full(len(vertices), -1, dtype=np.int64)
            remap[mask] = np.arange(mask.sum())
            valid_faces = np.all(mask[faces], axis=1)
            vertices = vertices[mask]
            faces = remap[faces[valid_faces]]
        valid = np.all((faces >= 0) & (faces < len(vertices)), axis=1)
        faces = faces[valid]
        return MeshPart(self.name, vertices, faces, self.color)


def merge_parts(name: str, parts: Iterable[MeshPart], color: tuple[int, int, int, int]) -> MeshPart:
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
        return MeshPart(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    return MeshPart(name, np.vstack(vertices_list), np.vstack(faces_list), color).cleaned()
