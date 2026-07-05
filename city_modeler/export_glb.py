from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np
from PIL import Image
import trimesh
from trimesh.visual.texture import TextureVisuals

from .mesh_types import MeshPart


@dataclass(slots=True)
class RenderTextureConfig:
    ground_texture: str | Path | None = None
    wall_texture: str | Path | None = None
    roof_texture: str | Path | None = None
    wall_repeat_mm: float = 12.0
    roof_repeat_mm: float = 18.0

    def has_any(self) -> bool:
        return any(self._existing_paths())

    def _existing_paths(self) -> list[Path]:
        paths: list[Path] = []
        for value in (self.ground_texture, self.wall_texture, self.roof_texture):
            if not value:
                continue
            path = Path(value)
            if path.exists() and path.is_file():
                paths.append(path)
        return paths

    def summary(self) -> dict[str, object]:
        return {
            "enabled": self.has_any(),
            "ground": bool(self.ground_texture and Path(self.ground_texture).exists()),
            "walls": bool(self.wall_texture and Path(self.wall_texture).exists()),
            "roofs": bool(self.roof_texture and Path(self.roof_texture).exists()),
            "wall_repeat_mm": float(self.wall_repeat_mm),
            "roof_repeat_mm": float(self.roof_repeat_mm),
        }


BUILDING_TEXTURE_PARTS = {"buildings"}
GROUND_TEXTURE_PARTS = {"terrain"}


def _face_normal_z(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    triangles = vertices[faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    safe_lengths = np.where(lengths > 1e-12, lengths, 1.0)
    return normals[:, 2] / safe_lengths


def _scene_bounds(parts: list[MeshPart]) -> tuple[float, float, float, float]:
    vertices = [part.vertices for part in parts if not part.is_empty()]
    if not vertices:
        return (0.0, 1.0, 0.0, 1.0)
    all_vertices = np.vstack(vertices)
    min_x = float(np.nanmin(all_vertices[:, 0]))
    max_x = float(np.nanmax(all_vertices[:, 0]))
    min_y = float(np.nanmin(all_vertices[:, 1]))
    max_y = float(np.nanmax(all_vertices[:, 1]))
    if abs(max_x - min_x) < 1e-9:
        max_x = min_x + 1.0
    if abs(max_y - min_y) < 1e-9:
        max_y = min_y + 1.0
    return (min_x, max_x, min_y, max_y)


def _colored_mesh(part: MeshPart, face_indices: np.ndarray | None = None) -> trimesh.Trimesh | None:
    faces = part.faces if face_indices is None else part.faces[face_indices]
    if len(faces) == 0:
        return None
    mesh = trimesh.Trimesh(vertices=part.vertices, faces=faces, process=False)
    color = np.array(part.color, dtype=np.uint8)
    mesh.visual.face_colors = np.tile(color, (len(mesh.faces), 1))
    return mesh


def _planar_uv(point: np.ndarray, bounds: tuple[float, float, float, float]) -> tuple[float, float]:
    min_x, max_x, min_y, max_y = bounds
    u = (float(point[0]) - min_x) / max(max_x - min_x, 1e-9)
    v = 1.0 - (float(point[1]) - min_y) / max(max_y - min_y, 1e-9)
    return (u, v)


def _wall_uv(point: np.ndarray, normal: np.ndarray, repeat_mm: float) -> tuple[float, float]:
    repeat = max(float(repeat_mm), 0.5)
    horizontal = float(point[1] if abs(normal[0]) >= abs(normal[1]) else point[0])
    return (horizontal / repeat, float(point[2]) / repeat)


def _textured_mesh(
    part: MeshPart,
    face_indices: np.ndarray,
    image_path: str | Path,
    *,
    mode: str,
    bounds: tuple[float, float, float, float],
    repeat_mm: float,
) -> trimesh.Trimesh | None:
    if len(face_indices) == 0:
        return None
    vertices: list[np.ndarray] = []
    faces: list[list[int]] = []
    uv: list[tuple[float, float]] = []
    source_vertices = part.vertices
    source_faces = part.faces
    for local_face_index, face_index in enumerate(face_indices):
        tri_indices = source_faces[face_index]
        triangle = source_vertices[tri_indices]
        normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        start = len(vertices)
        faces.append([start, start + 1, start + 2])
        for point in triangle:
            vertices.append(point)
            if mode == "wall":
                uv.append(_wall_uv(point, normal, repeat_mm))
            elif mode == "repeat_planar":
                repeat = max(float(repeat_mm), 0.5)
                uv.append((float(point[0]) / repeat, 1.0 - float(point[1]) / repeat))
            else:
                uv.append(_planar_uv(point, bounds))
    mesh = trimesh.Trimesh(vertices=np.asarray(vertices, dtype=float), faces=np.asarray(faces, dtype=np.int64), process=False)
    with Image.open(image_path) as image:
        texture_image = image.convert("RGBA").copy()
    mesh.visual = TextureVisuals(uv=np.asarray(uv, dtype=float), image=texture_image)
    return mesh


def _add_textured_part(
    scene: trimesh.Scene,
    part: MeshPart,
    textures: RenderTextureConfig,
    bounds: tuple[float, float, float, float],
) -> int:
    face_indices = np.arange(len(part.faces))
    normal_z = _face_normal_z(part.vertices, part.faces)
    added = 0

    if part.name in GROUND_TEXTURE_PARTS and textures.ground_texture:
        top_faces = face_indices[normal_z > 0.20]
        other_faces = face_indices[normal_z <= 0.20]
        textured = _textured_mesh(part, top_faces, textures.ground_texture, mode="planar", bounds=bounds, repeat_mm=textures.roof_repeat_mm)
        if textured is not None:
            scene.add_geometry(textured, geom_name=f"{part.name}_ground_texture", node_name=f"{part.name}_ground_texture")
            added += 1
        colored = _colored_mesh(part, other_faces)
        if colored is not None:
            scene.add_geometry(colored, geom_name=f"{part.name}_color", node_name=f"{part.name}_color")
            added += 1
        return added

    if part.name in BUILDING_TEXTURE_PARTS and (textures.wall_texture or textures.roof_texture):
        wall_faces = face_indices[np.abs(normal_z) < 0.35] if textures.wall_texture else np.array([], dtype=np.int64)
        roof_faces = face_indices[normal_z > 0.35] if textures.roof_texture else np.array([], dtype=np.int64)
        textured_faces = np.zeros(len(part.faces), dtype=bool)
        textured_faces[wall_faces] = True
        textured_faces[roof_faces] = True
        other_faces = face_indices[~textured_faces]

        if textures.wall_texture:
            textured = _textured_mesh(part, wall_faces, textures.wall_texture, mode="wall", bounds=bounds, repeat_mm=textures.wall_repeat_mm)
            if textured is not None:
                scene.add_geometry(textured, geom_name=f"{part.name}_wall_texture", node_name=f"{part.name}_wall_texture")
                added += 1
        if textures.roof_texture:
            textured = _textured_mesh(part, roof_faces, textures.roof_texture, mode="repeat_planar", bounds=bounds, repeat_mm=textures.roof_repeat_mm)
            if textured is not None:
                scene.add_geometry(textured, geom_name=f"{part.name}_roof_texture", node_name=f"{part.name}_roof_texture")
                added += 1
        colored = _colored_mesh(part, other_faces)
        if colored is not None:
            scene.add_geometry(colored, geom_name=f"{part.name}_color", node_name=f"{part.name}_color")
            added += 1
        return added

    colored = _colored_mesh(part)
    if colored is not None:
        scene.add_geometry(colored, geom_name=part.name, node_name=part.name)
        added += 1
    return added


def write_glb(parts: list[MeshPart], path: str | Path, textures: RenderTextureConfig | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene = trimesh.Scene()
    added = 0
    cleaned_parts = [part.cleaned() for part in parts]
    bounds = _scene_bounds(cleaned_parts)
    texture_config = textures if textures and textures.has_any() else None
    for part in cleaned_parts:
        if part.is_empty():
            continue
        if texture_config is not None:
            added += _add_textured_part(scene, part, texture_config, bounds)
        else:
            mesh = _colored_mesh(part)
            if mesh is not None:
                scene.add_geometry(mesh, geom_name=part.name, node_name=part.name)
                added += 1
    if added == 0:
        raise ValueError("No mesh parts to write into GLB.")
    data = scene.export(file_type="glb")
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    return path
