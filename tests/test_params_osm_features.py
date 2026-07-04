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


def test_model_params_airport_layer_defaults_on():
    params = ModelParams.from_dict({"bbox": [47.62, -122.355, 47.626, -122.3455]})

    assert params.include_airport is True


def test_model_params_rail_and_subway_layers_default_off_and_can_enable():
    params = ModelParams.from_dict({"bbox": [47.62, -122.355, 47.626, -122.3455]})

    assert params.include_rail_lines is False
    assert params.include_rail_stations is False
    assert params.include_subway_lines is False
    assert params.include_subway_stations is False

    enabled = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "include_rail_lines": "true",
        "include_rail_stations": "true",
        "include_subway_lines": "true",
        "include_subway_stations": "true",
    })

    assert enabled.include_rail_lines is True
    assert enabled.include_rail_stations is True
    assert enabled.include_subway_lines is True
    assert enabled.include_subway_stations is True


def test_model_params_area_infill_defaults_on_with_06mm_height():
    params = ModelParams.from_dict({"bbox": [47.62, -122.355, 47.626, -122.3455]})

    assert params.include_area_infill is True
    assert params.area_infill_height_mm == 0.60
    assert params.area_infill_mode == "empty_areas"
    assert params.model_detail_mode == "normal"


def test_model_params_accepts_high_detail_mode():
    params = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "model_detail_mode": "high",
    })

    assert params.model_detail_mode == "high"


def test_model_params_accepts_area_infill_height_and_toggle():
    params = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "area_infill_height_mm": "0.8",
        "area_infill_mode": "all_areas",
        "include_area_infill": "false",
    })

    assert params.area_infill_height_mm == 0.8
    assert params.area_infill_mode == "all_areas"
    assert params.include_area_infill is False


def test_model_params_auto_repair_mesh_defaults_on_and_can_disable():
    params = ModelParams.from_dict({"bbox": [47.62, -122.355, 47.626, -122.3455]})

    assert params.auto_repair_mesh is True
    assert params.export_print_color_groups is True

    disabled = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "auto_repair_mesh": "false",
        "export_print_color_groups": "false",
    })

    assert disabled.auto_repair_mesh is False
    assert disabled.export_print_color_groups is False


def test_model_params_accepts_old_random_export_colors_alias():
    params = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "random_export_colors": "false",
    })

    assert params.export_print_color_groups is False


def test_model_params_accepts_saved_route_segments():
    params = ModelParams.from_dict({
        "bbox": [47.62, -122.355, 47.626, -122.3455],
        "include_route": "true",
        "route_width_mm": "1.4",
        "route_height_mm": "0.9",
        "route_offset_mm": "0.2",
        "route_name": "walk.gpx",
        "route_segments": [[[47.621, -122.352], [47.622, -122.351]]],
    })

    assert params.include_route is True
    assert params.route_width_mm == 1.4
    assert params.route_height_mm == 0.9
    assert params.route_offset_mm == 0.2
    assert params.route_name == "walk.gpx"
    assert params.route_segments == [[[47.621, -122.352], [47.622, -122.351]]]


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


def test_parse_water_relation_uses_separate_member_way_geometry():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)

    def point(lon, lat):
        return {"lon": lon, "lat": lat}

    osm_json = {
        "elements": [
            {"type": "way", "id": 11, "geometry": [point(-121.999, 47.001), point(-121.991, 47.001)]},
            {"type": "way", "id": 12, "geometry": [point(-121.991, 47.001), point(-121.991, 47.009)]},
            {"type": "way", "id": 13, "geometry": [point(-121.991, 47.009), point(-121.999, 47.009)]},
            {"type": "way", "id": 14, "geometry": [point(-121.999, 47.009), point(-121.999, 47.001)]},
            {
                "type": "relation",
                "id": 10,
                "tags": {"type": "multipolygon", "natural": "water", "water": "lake"},
                "members": [
                    {"type": "way", "role": "outer", "ref": 11},
                    {"type": "way", "role": "outer", "ref": 12},
                    {"type": "way", "role": "outer", "ref": 13},
                    {"type": "way", "role": "outer", "ref": 14},
                ],
            },
        ]
    }

    features = parse_osm_features(osm_json, projection)
    water = [feature for feature in features if feature.layer == "water"]

    assert len(water) == 1
    assert water[0].osm_id == "relation/10"
    assert water[0].geometry_m.area > 0


def test_closed_waterway_river_is_line_not_filled_polygon():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)
    ring = [
        {"lon": -121.998, "lat": 47.002},
        {"lon": -121.992, "lat": 47.002},
        {"lon": -121.992, "lat": 47.008},
        {"lon": -121.998, "lat": 47.008},
        {"lon": -121.998, "lat": 47.002},
    ]
    osm_json = {
        "elements": [
            {
                "type": "way",
                "id": 101,
                "tags": {"waterway": "river", "name": "Loop River"},
                "geometry": ring,
            },
            {
                "type": "way",
                "id": 102,
                "tags": {"waterway": "riverbank"},
                "geometry": [
                    {"lon": -121.997, "lat": 47.003},
                    {"lon": -121.996, "lat": 47.003},
                    {"lon": -121.996, "lat": 47.004},
                    {"lon": -121.997, "lat": 47.004},
                    {"lon": -121.997, "lat": 47.003},
                ],
            },
        ]
    }

    features = parse_osm_features(osm_json, projection)
    river = next(feature for feature in features if feature.osm_id == "way/101")
    lake = next(feature for feature in features if feature.osm_id == "way/102")

    assert river.layer == "water"
    assert river.geometry_m.area == 0
    assert river.geometry_m.length > 0
    assert lake.layer == "water"
    assert lake.geometry_m.area > 0


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


def test_parse_broad_area_tags_as_area_infill():
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
            square(6, {"historic": "district", "landuse": "residential", "place": "city_block", "tourism": "theme_park"}, 0.0000),
            square(7, {"amenity": "hospital"}, 0.0010),
            square(8, {"building": "yes", "landuse": "residential"}, 0.0020),
        ]
    }

    features = parse_osm_features(osm_json, projection)
    area_infill = [feature for feature in features if feature.layer == "area_infill"]
    buildings = [feature for feature in features if feature.layer == "building"]

    assert {feature.osm_id for feature in area_infill} == {"way/6", "way/7"}
    assert {feature.osm_id for feature in buildings} == {"way/8"}


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


def test_parse_airport_runway_taxiway_and_apron():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)

    def point(lon, lat):
        return {"lon": lon, "lat": lat}

    osm_json = {
        "elements": [
            {
                "type": "way",
                "id": 40,
                "tags": {"aeroway": "runway", "width": "45 m"},
                "geometry": [point(-121.999, 47.001), point(-121.991, 47.001)],
            },
            {
                "type": "way",
                "id": 41,
                "tags": {"aeroway": "taxiway"},
                "geometry": [point(-121.999, 47.002), point(-121.991, 47.002)],
            },
            {
                "type": "way",
                "id": 42,
                "tags": {"aeroway": "apron"},
                "geometry": [
                    point(-121.998, 47.003), point(-121.996, 47.003),
                    point(-121.996, 47.005), point(-121.998, 47.005),
                    point(-121.998, 47.003),
                ],
            },
        ]
    }

    features = parse_osm_features(osm_json, projection)
    airport = [feature for feature in features if feature.layer == "airport"]

    assert len(airport) == 3
    assert {feature.osm_id for feature in airport} == {"way/40", "way/41", "way/42"}


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


def test_parse_rail_and_subway_lines_and_stations():
    projection = make_local_projection(47.0, -122.0, 47.01, -121.99)
    osm_json = {
        "elements": [
            {
                "type": "way",
                "id": 10,
                "tags": {"railway": "rail"},
                "geometry": [{"lon": -121.999, "lat": 47.001}, {"lon": -121.991, "lat": 47.001}],
            },
            {
                "type": "way",
                "id": 11,
                "tags": {"railway": "subway", "tunnel": "yes"},
                "geometry": [{"lon": -121.999, "lat": 47.002}, {"lon": -121.991, "lat": 47.002}],
            },
            {
                "type": "node",
                "id": 12,
                "tags": {"railway": "station"},
                "lon": -121.995,
                "lat": 47.003,
            },
            {
                "type": "node",
                "id": 13,
                "tags": {"railway": "station", "station": "subway"},
                "lon": -121.994,
                "lat": 47.004,
            },
        ]
    }

    features = parse_osm_features(osm_json, projection)

    assert {feature.layer for feature in features} == {"rail_line", "subway_line", "rail_station", "subway_station"}
    assert {feature.osm_id for feature in features if feature.layer == "rail_station"} == {"node/12"}
    assert {feature.osm_id for feature in features if feature.layer == "subway_station"} == {"node/13"}
