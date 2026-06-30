from city_modeler.geo import make_local_projection
from city_modeler.osm import parse_osm_features
from city_modeler.params import DEFAULT_ROAD_LEVELS, ModelParams


def test_model_params_accepts_road_levels():
    params = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "road_levels": ["primary", "residential", "footway", "unknown"],
    })

    assert params.road_levels == ["primary", "residential", "footway"]


def test_model_params_default_road_levels_include_footway_and_pedestrian():
    params = ModelParams.from_dict({"bbox": [47.62, -122.355, 47.626, -122.3455]})

    assert params.road_levels == DEFAULT_ROAD_LEVELS
    assert "footway" in params.road_levels
    assert "pedestrian" in params.road_levels
    assert "service" not in params.road_levels
    assert "path" not in params.road_levels


def test_model_params_default_footway_and_pedestrian_widths_are_06():
    params = ModelParams.from_dict({"bbox": [47.62, -122.355, 47.626, -122.3455]})

    assert params.footway_width_mm == 0.60
    assert params.pedestrian_width_mm == 0.60


def test_model_params_accepts_auto_terrain():
    params = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "auto_terrain": "true",
    })

    assert params.auto_terrain is True


def test_model_params_accepts_large_map_mode():
    params = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "large_map_mode": "true",
        "terrain_tile_zoom": "13",
        "osm_tile_size_km": "2.5",
    })

    assert params.large_map_mode is True
    assert params.terrain_tile_zoom == 13
    assert params.osm_tile_size_km == 2.5


def test_model_params_accepts_cut_out_water():
    params = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "cut_out_water": "true",
    })

    assert params.cut_out_water is True


def test_model_params_accepts_independent_footway_and_pedestrian_widths():
    params = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "footway_width_mm": "0.4",
        "pedestrian_width_mm": "0.7",
    })

    assert params.footway_width_mm == 0.4
    assert params.pedestrian_width_mm == 0.7


def test_model_params_accepts_selection_shape():
    params = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "selection_shape": "hexagon",
    })

    assert params.selection_shape == "hexagon"


def test_parse_water_relation_members():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)

    def point(lon, lat):
        return {"lon": lon, "lat": lat}

    osm_json = {
        "elements": [{
            "type": "relation",
            "id": 1,
            "tags": {"type": "multipolygon", "natural": "water", "water": "lake"},
            "members": [
                {"type": "way", "role": "outer", "geometry": [point(-121.999, 47.001), point(-121.991, 47.001)]},
                {"type": "way", "role": "outer", "geometry": [point(-121.991, 47.001), point(-121.991, 47.009)]},
                {"type": "way", "role": "outer", "geometry": [point(-121.991, 47.009), point(-121.999, 47.009)]},
                {"type": "way", "role": "outer", "geometry": [point(-121.999, 47.009), point(-121.999, 47.001)]},
            ],
        }]
    }

    features = parse_osm_features(osm_json, projection)
    water = [feature for feature in features if feature.layer == "water"]

    assert len(water) == 1
    assert water[0].geometry_m.area > 0


def test_parse_building_part_way():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)
    osm_json = {
        "elements": [{
            "type": "way",
            "id": 2,
            "tags": {"building:part": "yes", "building:levels": "3"},
            "geometry": [
                {"lon": -121.999, "lat": 47.001},
                {"lon": -121.997, "lat": 47.001},
                {"lon": -121.997, "lat": 47.003},
                {"lon": -121.999, "lat": 47.003},
                {"lon": -121.999, "lat": 47.001},
            ],
        }]
    }

    features = parse_osm_features(osm_json, projection)

    assert len(features) == 1
    assert features[0].layer == "building"


def test_parse_green_relation_members_and_wetland():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)

    def point(lon, lat):
        return {"lon": lon, "lat": lat}

    osm_json = {
        "elements": [
            {
                "type": "relation",
                "id": 3,
                "tags": {"type": "multipolygon", "leisure": "park"},
                "members": [
                    {"type": "way", "role": "outer", "geometry": [point(-121.999, 47.001), point(-121.991, 47.001)]},
                    {"type": "way", "role": "outer", "geometry": [point(-121.991, 47.001), point(-121.991, 47.009)]},
                    {"type": "way", "role": "outer", "geometry": [point(-121.991, 47.009), point(-121.999, 47.009)]},
                    {"type": "way", "role": "outer", "geometry": [point(-121.999, 47.009), point(-121.999, 47.001)]},
                ],
            },
            {
                "type": "way",
                "id": 4,
                "tags": {"natural": "wetland"},
                "geometry": [
                    point(-121.998, 47.002), point(-121.997, 47.002),
                    point(-121.997, 47.003), point(-121.998, 47.003),
                    point(-121.998, 47.002),
                ],
            },
        ]
    }

    features = parse_osm_features(osm_json, projection)
    green = [feature for feature in features if feature.layer == "green"]
    water = [feature for feature in features if feature.layer == "water"]

    assert len(green) == 2
    assert water == []


def test_parse_landcover_as_green():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)
    osm_json = {
        "elements": [{
            "type": "way",
            "id": 5,
            "tags": {"landcover": "grass"},
            "geometry": [
                {"lon": -121.998, "lat": 47.002},
                {"lon": -121.997, "lat": 47.002},
                {"lon": -121.997, "lat": 47.003},
                {"lon": -121.998, "lat": 47.003},
                {"lon": -121.998, "lat": 47.002},
            ],
        }]
    }

    features = parse_osm_features(osm_json, projection)

    assert len(features) == 1
    assert features[0].layer == "green"


def test_parse_hedge_and_low_planting_areas_as_green():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)

    def square(osm_id, tags, lon_offset):
        west = -121.999 + lon_offset
        east = west + 0.0005
        return {
            "type": "way",
            "id": osm_id,
            "tags": tags,
            "geometry": [
                {"lon": west, "lat": 47.001},
                {"lon": east, "lat": 47.001},
                {"lon": east, "lat": 47.002},
                {"lon": west, "lat": 47.002},
                {"lon": west, "lat": 47.001},
            ],
        }

    osm_json = {
        "elements": [
            square(30, {"barrier": "hedge"}, 0.0000),
            square(31, {"barrier": "planter"}, 0.0010),
            square(32, {"man_made": "planter"}, 0.0020),
            square(33, {"natural": "shrubbery"}, 0.0030),
            square(34, {"landuse": "flowerbed"}, 0.0040),
            {
                "type": "way",
                "id": 35,
                "tags": {"barrier": "hedge"},
                "geometry": [
                    {"lon": -121.999, "lat": 47.004},
                    {"lon": -121.998, "lat": 47.004},
                ],
            },
        ]
    }

    features = parse_osm_features(osm_json, projection)
    green = [feature for feature in features if feature.layer == "green"]

    assert len(green) == 5
    assert {feature.osm_id for feature in green} == {"way/30", "way/31", "way/32", "way/33", "way/34"}


def test_parse_surface_parking_only():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)

    def square(osm_id, tags, lon_offset):
        west = -121.999 + lon_offset
        east = west + 0.0005
        return {
            "type": "way",
            "id": osm_id,
            "tags": tags,
            "geometry": [
                {"lon": west, "lat": 47.001},
                {"lon": east, "lat": 47.001},
                {"lon": east, "lat": 47.002},
                {"lon": west, "lat": 47.002},
                {"lon": west, "lat": 47.001},
            ],
        }

    osm_json = {
        "elements": [
            square(20, {"amenity": "parking", "parking": "surface"}, 0.0000),
            square(21, {"amenity": "parking", "parking": "multi-storey"}, 0.0010),
            square(22, {"amenity": "parking", "parking": "underground"}, 0.0020),
            square(23, {"amenity": "parking", "parking": "rooftop"}, 0.0030),
            square(24, {"amenity": "parking", "covered": "yes"}, 0.0040),
        ]
    }

    features = parse_osm_features(osm_json, projection)
    parking = [feature for feature in features if feature.layer == "parking"]

    assert len(parking) == 1
    assert parking[0].osm_id == "way/20"


def test_parse_coastline_creates_water_side_polygon():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)
    osm_json = {
        "elements": [{
            "type": "way",
            "id": 10,
            "tags": {"natural": "coastline"},
            "geometry": [
                {"lon": -121.995, "lat": 47.000},
                {"lon": -121.995, "lat": 47.010},
            ],
        }]
    }

    features = parse_osm_features(osm_json, projection)
    water = [feature for feature in features if feature.layer == "water"]

    assert len(water) == 1
    assert water[0].tags["water"] == "sea"
    assert water[0].geometry_m.area > 0
