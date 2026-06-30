from __future__ import annotations

from typing import Any

import numpy as np
import trimesh
import trimesh.repair

from .mesh_types import MeshPart


def mesh_diagnostics(part: MeshPart) -> dict[str, Any]:
    part = part.cleaned()
    if part.is_empty():
        return {
            "vertices": 0,
            "triangles": 0,
            "watertight": False,
            "boundary_edges": 0,
            "overused_edges": 0,
            "non_manifold_edges": 0,
        }
    mesh = trimesh.Trimesh(vertices=part.vertices, faces=part.faces, process=False)
    if len(mesh.edges_unique) == 0:
        boundary_edges = 0
        overused_edges = 0
        non_manifold_edges = 0
    else:
        counts = np.bincount(mesh.edges_unique_inverse, minlength=len(mesh.edges_unique))
        boundary_edges = int(np.count_nonzero(counts == 1))
        overused_edges = int(np.count_nonzero(counts > 2))
        non_manifold_edges = int(np.count_nonzero(counts != 2))
    return {
        "vertices": int(len(mesh.vertices)),
        "triangles": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "boundary_edges": boundary_edges,
        "overused_edges": overused_edges,
        "non_manifold_edges": non_manifold_edges,
    }


def repair_mesh_part(part: MeshPart) -> tuple[MeshPart, dict[str, Any]]:
    part = part.cleaned()
    before = mesh_diagnostics(part)
    if part.is_empty():
        return part, {"name": part.name, "before": before, "after": before, "fixed": {}}

    mesh = trimesh.Trimesh(vertices=part.vertices, faces=part.faces, process=False)
    degenerate_removed = 0
    duplicate_removed = 0

    if len(mesh.faces):
        nondegenerate = mesh.nondegenerate_faces(height=1e-10)
        degenerate_removed = int(len(mesh.faces) - int(np.count_nonzero(nondegenerate)))
        mesh.update_faces(nondegenerate)
        mesh.remove_unreferenced_vertices()

    if len(mesh.faces):
        unique = mesh.unique_faces()
        duplicate_removed = int(len(mesh.faces) - int(np.count_nonzero(unique)))
        mesh.update_faces(unique)
        mesh.remove_unreferenced_vertices()

    if len(mesh.vertices) and len(mesh.faces):
        mesh.merge_vertices(digits_vertex=5)
        mesh.remove_unreferenced_vertices()
        trimesh.repair.fix_winding(mesh)
        trimesh.repair.fix_normals(mesh, multibody=True)
        trimesh.repair.fix_inversion(mesh, multibody=True)
        filled_holes = bool(trimesh.repair.fill_holes(mesh))
        if len(mesh.faces):
            unique = mesh.unique_faces()
            duplicate_removed += int(len(mesh.faces) - int(np.count_nonzero(unique)))
            mesh.update_faces(unique)
        mesh.remove_unreferenced_vertices()
    else:
        filled_holes = False

    repaired = MeshPart(part.name, np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=np.int64), part.color).cleaned()
    after = mesh_diagnostics(repaired)
    report = {
        "name": part.name,
        "before": before,
        "after": after,
        "fixed": {
            "degenerate_faces_removed": degenerate_removed,
            "duplicate_faces_removed": duplicate_removed,
            "filled_simple_holes": filled_holes,
            "vertices_delta": int(after["vertices"] - before["vertices"]),
            "triangles_delta": int(after["triangles"] - before["triangles"]),
            "non_manifold_edges_delta": int(after["non_manifold_edges"] - before["non_manifold_edges"]),
        },
    }
    return repaired, report


def repair_mesh_parts(parts: list[MeshPart], enabled: bool = True) -> tuple[list[MeshPart], dict[str, Any]]:
    if not enabled:
        diagnostics = [mesh_diagnostics(part) | {"name": part.name} for part in parts]
        return parts, {
            "enabled": False,
            "status": "disabled",
            "parts": diagnostics,
            "totals": _totals_from_diagnostics(diagnostics),
        }

    repaired_parts: list[MeshPart] = []
    reports: list[dict[str, Any]] = []
    for part in parts:
        repaired, report = repair_mesh_part(part)
        if not repaired.is_empty():
            repaired_parts.append(repaired)
        reports.append(report)

    before_total = _totals_from_diagnostics([report["before"] for report in reports])
    after_total = _totals_from_diagnostics([report["after"] for report in reports])
    if after_total["non_manifold_edges"] == 0:
        status = "clean"
    elif after_total["non_manifold_edges"] < before_total["non_manifold_edges"]:
        status = "improved"
    else:
        status = "issues_remaining"

    return repaired_parts, {
        "enabled": True,
        "status": status,
        "parts": reports,
        "totals": {
            "before": before_total,
            "after": after_total,
        },
    }


def _totals_from_diagnostics(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "vertices": int(sum(int(item.get("vertices", 0)) for item in items)),
        "triangles": int(sum(int(item.get("triangles", 0)) for item in items)),
        "boundary_edges": int(sum(int(item.get("boundary_edges", 0)) for item in items)),
        "overused_edges": int(sum(int(item.get("overused_edges", 0)) for item in items)),
        "non_manifold_edges": int(sum(int(item.get("non_manifold_edges", 0)) for item in items)),
    }
