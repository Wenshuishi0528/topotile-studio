from pathlib import Path
import zipfile

from city_modeler.params import ModelParams
from city_modeler.pipeline import generate_model, generate_sample, make_synthetic_osm_json
from city_modeler.export_3mf import validate_3mf


def test_generate_sample(tmp_path: Path):
    summary = generate_sample(tmp_path)
    assert (tmp_path / "city_model.3mf").exists()
    assert (tmp_path / "city_model.glb").exists()
    assert summary["features"]["buildings"] > 0
    assert summary["features"]["parking"] > 0
    info = validate_3mf(tmp_path / "city_model.3mf")
    assert info["objects"] >= 2
    assert info["triangles"] > 0


def test_generate_cut_out_water_removes_water_mesh(tmp_path: Path):
    params = ModelParams(
        south=47.6200,
        west=-122.3550,
        north=47.6260,
        east=-122.3455,
        max_size_mm=160,
        terrain_grid_size=36,
        cut_out_water=True,
    )
    osm_json = make_synthetic_osm_json(params.south, params.west, params.north, params.east)

    summary = generate_model(params, tmp_path, osm_json_override=osm_json)

    assert summary["water_cutout"]["enabled"] is True
    assert summary["water_cutout"]["polygons"] > 0
    assert "water" not in {part["name"] for part in summary["mesh_parts"]}
    assert (tmp_path / "city_model.3mf").exists()


def test_generate_circle_footprint(tmp_path: Path):
    params = ModelParams(
        south=47.6200,
        west=-122.3550,
        north=47.6260,
        east=-122.3455,
        max_size_mm=160,
        terrain_grid_size=36,
        selection_shape="circle",
    )
    osm_json = make_synthetic_osm_json(params.south, params.west, params.north, params.east)

    summary = generate_model(params, tmp_path, osm_json_override=osm_json)

    assert summary["selection_shape"] == "circle"
    assert (tmp_path / "city_model.3mf").exists()


def test_generate_hexagon_footprint(tmp_path: Path):
    params = ModelParams(
        south=47.6200,
        west=-122.3550,
        north=47.6260,
        east=-122.3455,
        max_size_mm=160,
        terrain_grid_size=36,
        selection_shape="hexagon",
    )
    osm_json = make_synthetic_osm_json(params.south, params.west, params.north, params.east)

    summary = generate_model(params, tmp_path, osm_json_override=osm_json)

    assert summary["selection_shape"] == "hexagon"
    assert (tmp_path / "city_model.3mf").exists()


def test_generate_uses_custom_output_name(tmp_path: Path):
    params = ModelParams(
        south=47.6200,
        west=-122.3550,
        north=47.6260,
        east=-122.3455,
        max_size_mm=160,
        terrain_grid_size=18,
        output_name="UW Campus.3mf",
    )
    osm_json = make_synthetic_osm_json(params.south, params.west, params.north, params.east)

    summary = generate_model(params, tmp_path, osm_json_override=osm_json)

    assert summary["output_name"] == "UW_Campus"
    assert summary["files"]["3mf"] == "UW_Campus.3mf"
    assert summary["files"]["glb"] == "UW_Campus.glb"
    assert summary["files"]["stl"] == "UW_Campus.stl"
    validate_3mf(tmp_path / "UW_Campus.3mf")


def test_generate_numbered_chunk_export(tmp_path: Path):
    params = ModelParams(
        south=47.6200,
        west=-122.3550,
        north=47.6260,
        east=-122.3455,
        max_size_mm=160,
        terrain_grid_size=18,
        chunk_export=True,
        chunk_rows=2,
        chunk_cols=2,
        output_name="campus tile",
    )
    osm_json = make_synthetic_osm_json(params.south, params.west, params.north, params.east)

    summary = generate_model(params, tmp_path, osm_json_override=osm_json)

    assert summary["chunk_export"]["enabled"] is True
    assert summary["chunk_export"]["pieces"] == 4
    assert summary["printability"]["score"] > 0
    zip_path = tmp_path / "campus_tile_chunks.zip"
    manifest_path = tmp_path / "campus_tile_chunks_manifest.json"
    assert zip_path.exists()
    assert manifest_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "campus_tile_chunks_manifest.json" in names
    assert "campus_tile_r01_c01.3mf" in names
    validate_3mf(tmp_path / "chunks" / "r01_c01" / "campus_tile_r01_c01.3mf")
