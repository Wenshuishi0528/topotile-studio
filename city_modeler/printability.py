from __future__ import annotations

from typing import Any

from .params import ModelParams


def printability_report(params: ModelParams, summary: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    score = 100

    def add(level: str, penalty: int, message: str, suggestion: str) -> None:
        nonlocal score
        score -= penalty
        issues.append({
            "level": level,
            "message": message,
            "suggestion": suggestion,
        })

    model_width = float(summary.get("model_width_mm", 0))
    model_height = float(summary.get("model_height_mm", 0))
    max_xy = max(model_width, model_height)
    if max_xy > 235:
        add("error", 22, "Model is very close to the Bambu A1 build-plate limit.", "Reduce Max XY size or enable chunk export.")
    elif max_xy > 220:
        add("warning", 10, "Model leaves little edge margin on the build plate.", "Use a slightly smaller Max XY size.")

    if params.base_thickness_mm < 1.2:
        add("error", 18, "Base is thin for a terrain/city tile.", "Use at least 1.2 mm base thickness; 2-3 mm is safer.")
    elif params.base_thickness_mm < 2.0:
        add("warning", 8, "Base may flex after printing.", "Use a thicker base for larger tiles.")

    if params.include_roads:
        selected = set(params.road_levels)
        if params.min_road_width_mm < 0.45:
            add("warning", 8, "Some road geometry may be too narrow to print clearly.", "Raise Min road width to 0.5 mm or higher.")
        if "footway" in selected and params.footway_width_mm < 0.45:
            add("warning", 6, "Footways are set very thin.", "Raise Footway width if the printer misses small paths.")
        if "pedestrian" in selected and params.pedestrian_width_mm < 0.45:
            add("warning", 6, "Pedestrian roads are set very thin.", "Raise Pedestrian width if plazas or paths disappear.")

    terrain = summary.get("terrain") or {}
    relief = float(terrain.get("relief_mm", 0))
    if relief > 55:
        add("warning", 10, "Terrain relief is high for a small desktop print.", "Lower vertical exaggeration or max terrain height.")
    elif relief > 40:
        add("info", 4, "Terrain relief is fairly strong.", "Check the side profile before printing.")

    validation = summary.get("validation_3mf") or {}
    triangles = int(validation.get("triangles", 0))
    if triangles > 850_000:
        add("warning", 16, "3MF mesh is very dense and may load slowly in slicers.", "Lower terrain grid size or road detail.")
    elif triangles > 350_000:
        add("info", 6, "3MF mesh is moderately dense.", "If Bambu Studio feels slow, lower terrain grid size.")

    repair = summary.get("mesh_repair") or {}
    if repair.get("enabled"):
        totals = repair.get("totals") or {}
        after = totals.get("after") or {}
        before = totals.get("before") or {}
        remaining = int(after.get("non_manifold_edges", 0))
        fixed = int(before.get("non_manifold_edges", 0)) - remaining
        if remaining > 0:
            add("warning", 12, "Mesh repair found remaining non-manifold edges.", "Try reducing terrain/grid detail or road detail if Bambu Studio still reports repair issues.")
        elif fixed > 0:
            issues.append({
                "level": "info",
                "message": "Automatic mesh repair fixed non-manifold edges before export.",
                "suggestion": "Open the 3MF in Bambu Studio to confirm no additional repair prompt appears.",
            })
    else:
        issues.append({
            "level": "info",
            "message": "Automatic mesh repair is disabled.",
            "suggestion": "Enable mesh repair if Bambu Studio reports non-manifold edges.",
        })

    features = summary.get("features") or {}
    if params.include_buildings and int(features.get("buildings", 0)) == 0:
        add("info", 3, "No buildings were found in this selection.", "Move or enlarge the selection if buildings are expected.")
    if params.include_roads and int(features.get("roads", 0)) == 0:
        add("warning", 10, "No selected roads were generated.", "Enable more road levels or move the selection.")

    if params.chunk_export and params.chunk_rows * params.chunk_cols > 1:
        issues.append({
            "level": "info",
            "message": f"Chunk export is enabled: {params.chunk_rows} x {params.chunk_cols}.",
            "suggestion": "Use the numbered ZIP files for printing and stitching.",
        })

    score = max(0, min(100, score))
    if score >= 85:
        grade = "Good"
    elif score >= 70:
        grade = "Usable"
    elif score >= 50:
        grade = "Risky"
    else:
        grade = "Poor"

    return {
        "score": score,
        "grade": grade,
        "issues": issues,
    }
