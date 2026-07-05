from pathlib import Path

import numpy as np
from PIL import Image
import trimesh

from city_modeler.export_glb import RenderTextureConfig, write_glb
from city_modeler.mesh_types import MeshPart


def test_write_glb_embeds_render_texture_image(tmp_path: Path):
    texture = tmp_path / "wall.png"
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(texture)
    vertices = np.array([
        [0, 0, 0],
        [20, 0, 0],
        [20, 0, 20],
        [0, 0, 20],
    ], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    part = MeshPart("buildings", vertices, faces)

    path = write_glb(
        [part],
        tmp_path / "textured.glb",
        textures=RenderTextureConfig(wall_texture=texture),
    )

    data = path.read_bytes()
    assert b"PNG" in data
    scene = trimesh.load(path)
    assert sum(len(mesh.faces) for mesh in scene.geometry.values()) == 2
