from pathlib import Path
import zipfile

import pytest

from city_modeler.cancel import GenerationCancelled
from city_modeler.params import ModelParams
from city_modeler.pipeline import generate_model, generate_sample, make_synthetic_osm_json, should_fetch_supplemental_water
from city_modeler.export_3mf import validate_3mf


def test_generate_sample(tmp_path: Path):
    summary = generate_sample(tmp_path)
    files = summary["files"]
    assert summary["sample"]["name"] == "Offline test model"
    assert (tmp_path / files["3mf"]).exists()
    assert (tmp_path / files["glb"]).exists()
    assert (tmp_path / files["dae"]).exists()
    assert (tmp_path / files["stl"]).exists()
    assert (tmp_path / files["project"]).exists()
    assert summary["features"]["buildings"] > 0
    assert summary["features"]["roads"] > 0
    assert summary["features"]["bundled_sample_objects"] >= 5
    assert summary["mesh_repair"]["status"] == "bundled_sample"
    info = validate_3mf(tmp_path / files["3mf"])
    assert info["objects"] >= 2
    assert info["triangles"] > 0


def test_supplemental_water_fetch_triggers_by_size_not_large_map_mode():
    params = ModelParams(south=0.0, west=0.0, north=0.1, east=0.1, include_water=True, large_map_mode=False)

    assert should_fetch_supplemental_water(params, width_m=4500.0, height_m=4500.0) is True
    assert should_fetch_supplemental_water(params, width_m=8500.0, height_m=1000.0) is True
    assert should_fetch_supplemental_water(params, width_m=3000.0, height_m=3000.0) is False

    no_water = ModelParams(south=0.0, west=0.0, north=0.1, east=0.1, include_water=False, cut_out_water=False)
    assert should_fetch_supplemental_water(no_water, width_m=20_000.0, height_m=20_000.0) is False


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
    assert summary["overture_buildings"]["status"] == "skipped_override"
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
    assert summary["files"]["dae"] == "UW_Campus.dae"
    assert summary["files"]["stl"] == "UW_Campus.stl"
    validate_3mf(tmp_path / "UW_Campus.3mf")


def test_generate_with_manual_landmark_replacement(tmp_path: Path):
    import trimesh

    landmark_path = tmp_path / "landmark.stl"
    trimesh.creation.box(extents=(1.0, 1.0, 2.0)).export(landmark_path)
    params = ModelParams(
        south=47.6200,
        west=-122.3550,
        north=47.6260,
        east=-122.3455,
        max_size_mm=160,
        terrain_grid_size=18,
        include_landmark_replacement=True,
        landmark_osm_id="way/300",
        landmark_scale=1.0,
    )
    osm_json = make_synthetic_osm_json(params.south, params.west, params.north, params.east)

    summary = generate_model(params, tmp_path, landmark_model_path=landmark_path, osm_json_override=osm_json)

    assert summary["landmark_replacement"]["enabled"] is True
    assert summary["landmark_replacement"]["status"] == "complete"
    assert summary["landmark_replacement"]["matched_osm_id"] == "way/300"
    assert summary["landmark_replacement"]["removed_buildings"] >= 1
    assert summary["features"]["landmarks"] == 1
    assert summary["features"]["buildings"] == summary["features"]["osm_buildings"] - summary["landmark_replacement"]["removed_buildings"]
    assert "landmark" in {part["name"] for part in summary["mesh_parts"]}
    assert (tmp_path / "city_model.3mf").exists()


def test_generate_with_saved_route_segments(tmp_path: Path):
    params = ModelParams(
        south=47.6200,
        west=-122.3550,
        north=47.6260,
        east=-122.3455,
        max_size_mm=160,
        terrain_grid_size=18,
        include_route=True,
        route_name="sample.gpx",
        route_segments=[
            [
                [47.6210, -122.3530],
                [47.6225, -122.3510],
                [47.6240, -122.3480],
            ]
        ],
    )
    osm_json = make_synthetic_osm_json(params.south, params.west, params.north, params.east)

    summary = generate_model(params, tmp_path, osm_json_override=osm_json)

    assert summary["route"]["enabled"] is True
    assert summary["route"]["routes"] == 1
    assert summary["route"]["points"] == 3
    assert summary["route"]["clipped_segments"] >= 1
    assert "route" in {part["name"] for part in summary["mesh_parts"]}
    validate_3mf(tmp_path / "city_model.3mf")


def test_generate_with_multiple_saved_routes(tmp_path: Path):
    params = ModelParams(
        south=47.6200,
        west=-122.3550,
        north=47.6260,
        east=-122.3455,
        max_size_mm=160,
        terrain_grid_size=18,
        include_route=True,
        routes=[
            {
                "name": "walk.gpx",
                "segments": [[[47.6210, -122.3530], [47.6225, -122.3510]]],
                "width_mm": 0.8,
                "height_mm": 0.5,
                "offset_mm": 0.1,
            },
            {
                "name": "ride.kml",
                "segments": [[[47.6230, -122.3505], [47.6240, -122.3490], [47.6250, -122.3478]]],
                "width_mm": 1.4,
                "height_mm": 0.9,
                "offset_mm": 0.2,
            },
        ],
    )
    osm_json = make_synthetic_osm_json(params.south, params.west, params.north, params.east)

    summary = generate_model(params, tmp_path, osm_json_override=osm_json)

    assert summary["route"]["enabled"] is True
    assert summary["route"]["routes"] == 2
    assert summary["route"]["points"] == 5
    assert len(summary["routes"]) == 2
    assert summary["routes"][1]["name"] == "ride.kml"
    assert "route" in {part["name"] for part in summary["mesh_parts"]}
    validate_3mf(tmp_path / "city_model.3mf")


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


def test_generate_model_honors_cancel_check(tmp_path: Path):
    params = ModelParams(
        south=47.6200,
        west=-122.3550,
        north=47.6260,
        east=-122.3455,
    )

    def cancel_now():
        raise GenerationCancelled("Cancelled")

    with pytest.raises(GenerationCancelled):
        generate_model(params, tmp_path, osm_json_override={"elements": []}, cancel_check=cancel_now)
