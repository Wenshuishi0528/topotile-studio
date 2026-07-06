import json
from pathlib import Path

from city_modeler.geo import make_local_projection
from city_modeler.params import ModelParams
from city_modeler.pipeline import generate_model
from city_modeler.vector_data import parse_geojson_features


def sample_geojson() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "b1",
                "properties": {"topotile_layer": "building", "height": "18"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [116.3800, 39.9000],
                        [116.3810, 39.9000],
                        [116.3810, 39.9010],
                        [116.3800, 39.9010],
                        [116.3800, 39.9000],
                    ]],
                },
            },
            {
                "type": "Feature",
                "id": "r1",
                "properties": {"topotile_layer": "road", "highway": "primary"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[116.3795, 39.8995], [116.3815, 39.9015]],
                },
            },
            {
                "type": "Feature",
                "id": "w1",
                "properties": {"类别": "水体"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [116.3812, 39.9000],
                        [116.3818, 39.9000],
                        [116.3818, 39.9005],
                        [116.3812, 39.9005],
                        [116.3812, 39.9000],
                    ]],
                },
            },
            {
                "type": "Feature",
                "id": "g1",
                "properties": {"layer": "green"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [116.3795, 39.9011],
                        [116.3802, 39.9011],
                        [116.3802, 39.9018],
                        [116.3795, 39.9018],
                        [116.3795, 39.9011],
                    ]],
                },
            },
        ],
    }


def test_parse_geojson_features_maps_layers_and_coordinates():
    projection = make_local_projection(39.899, 116.379, 39.902, 116.382)

    features, summary = parse_geojson_features(sample_geojson(), projection, coordinate_system="wgs84")

    assert summary["features"] == 4
    assert summary["skipped"] == 0
    assert summary["layers"] == {"building": 1, "road": 1, "water": 1, "green": 1}
    by_id = {feature.osm_id: feature for feature in features}
    assert by_id["local/b1"].layer == "building"
    assert by_id["local/r1"].tags["highway"] == "primary"
    assert by_id["local/w1"].layer == "water"


def test_parse_geojson_features_maps_power_layers():
    projection = make_local_projection(39.899, 116.379, 39.902, 116.382)
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "pl1",
                "properties": {"topotile_layer": "power_line"},
                "geometry": {"type": "LineString", "coordinates": [[116.3795, 39.9000], [116.3815, 39.9000]]},
            },
            {
                "type": "Feature",
                "id": "mpl1",
                "properties": {"类别": "配电线"},
                "geometry": {"type": "LineString", "coordinates": [[116.3795, 39.9005], [116.3815, 39.9005]]},
            },
            {
                "type": "Feature",
                "id": "pt1",
                "properties": {"layer": "电塔"},
                "geometry": {"type": "Point", "coordinates": [116.3805, 39.9005]},
            },
            {
                "type": "Feature",
                "id": "pp1",
                "properties": {"图层": "发电厂"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [116.3800, 39.9010],
                        [116.3810, 39.9010],
                        [116.3810, 39.9018],
                        [116.3800, 39.9018],
                        [116.3800, 39.9010],
                    ]],
                },
            },
        ],
    }

    features, summary = parse_geojson_features(geojson, projection, coordinate_system="wgs84")

    assert summary["features"] == 4
    assert summary["layers"] == {
        "power_line": 1,
        "minor_power_line": 1,
        "power_tower": 1,
        "power_plant": 1,
    }
    assert {feature.layer for feature in features} == {
        "power_line", "minor_power_line", "power_tower", "power_plant"
    }


def test_generate_model_with_local_vector_geojson_replaces_osm(tmp_path: Path):
    vector_path = tmp_path / "china.geojson"
    vector_path.write_text(json.dumps(sample_geojson()), encoding="utf-8")
    params = ModelParams(
        south=39.899,
        west=116.379,
        north=39.902,
        east=116.382,
        max_size_mm=120,
        terrain_grid_size=18,
        model_data_source="local_vector",
        vector_coordinate_system="wgs84",
        vector_data_attribution="Authorized test vector data",
    )

    summary = generate_model(params, tmp_path, vector_data_path=vector_path)

    assert summary["model_data_source"]["source"] == "local_vector"
    assert summary["model_data_source"]["local_vector"]["features"] == 4
    assert summary["overture_buildings"]["status"] == "skipped_override"
    assert summary["features"]["buildings"] == 1
    assert summary["features"]["roads"] == 1
    assert summary["features"]["water"] == 1
    assert summary["features"]["green"] == 1
    assert (tmp_path / "city_model.3mf").exists()
    attribution = (tmp_path / "ATTRIBUTION.txt").read_text(encoding="utf-8")
    assert "Authorized test vector data" in attribution
