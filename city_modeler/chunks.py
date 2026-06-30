from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import zipfile
from typing import Any


@dataclass(slots=True)
class ChunkExportEntry:
    row: int
    col: int
    filename: str
    path: Path
    bbox: tuple[float, float, float, float]
    model_width_mm: float
    model_height_mm: float


def write_chunk_manifest(output_dir: Path, base_name: str, rows: int, cols: int, entries: list[ChunkExportEntry]) -> Path:
    manifest = {
        "rows": rows,
        "cols": cols,
        "numbering": "Rows are south-to-north; columns are west-to-east. Filename r01_c01 is the southwest piece.",
        "chunks": [
            {
                "row": entry.row,
                "col": entry.col,
                "filename": entry.filename,
                "bbox": entry.bbox,
                "model_width_mm": round(entry.model_width_mm, 3),
                "model_height_mm": round(entry.model_height_mm, 3),
            }
            for entry in entries
        ],
    }
    path = output_dir / f"{base_name}_chunks_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def write_chunk_zip(output_dir: Path, base_name: str, entries: list[ChunkExportEntry], manifest_path: Path) -> Path:
    zip_path = output_dir / f"{base_name}_chunks.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(manifest_path, arcname=manifest_path.name)
        for entry in entries:
            zf.write(entry.path, arcname=entry.filename)
    return zip_path


def chunk_summary(rows: int, cols: int, entries: list[ChunkExportEntry], zip_path: Path, manifest_path: Path) -> dict[str, Any]:
    return {
        "enabled": True,
        "rows": rows,
        "cols": cols,
        "pieces": len(entries),
        "zip": zip_path.name,
        "manifest": manifest_path.name,
        "numbering": "r01_c01 starts at the southwest corner; row increases northward, column increases eastward.",
        "files": [
            {
                "row": entry.row,
                "col": entry.col,
                "filename": entry.filename,
                "model_width_mm": round(entry.model_width_mm, 3),
                "model_height_mm": round(entry.model_height_mm, 3),
            }
            for entry in entries
        ],
    }
