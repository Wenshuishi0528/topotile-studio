import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from city_modeler.dem import TerrainGrid
from city_modeler.geo import ModelScaler
from city_modeler.mesh_ops import build_building_meshes, build_osm_roof_mesh, build_road_meshes, build_route_meshes, build_surface_layer_meshes, COLORS, extrude_polygon, is_bridge, road_width_m, road_width_mm, terrain_to_mesh
from city_modeler.mesh_repair import mesh_diagnostics
from city_modeler.osm import OSMFeature
from city_modeler.params import ModelParams


def test_road_width_parses_feet_inches():
    assert math.isclose(road_width_m({"highway": "tertiary", "width": "15'0\""}), 4.572, rel_tol=1e-4)
    assert math.isclose(road_width_m({"highway": "residential", "width": "12 ft"}), 3.6576, rel_tol=1e-4)
    assert math.isclose(road_width_m({"highway": "service", "width": "350 cm"}), 3.5, rel_tol=1e-4)


def test_footway_and_pedestrian_have_independent_print_widths():
    params = ModelParams(
        south=0.0,
        west=0.0,
        north=0.01,
        east=0.01,
        min_road_width_mm=1.2,
        footway_width_mm=0.4,
        pedestrian_width_mm=0.7,
    )
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 40.0], [0.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0], [40.0, 40.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    footway = OSMFeature(
        layer="road",
        geometry_m=LineString([(5.0, 5.0), (35.0, 5.0)]),
        tags={"highway": "footway"},
        osm_id="way/footway",
    )
    pedestrian = OSMFeature(
        layer="road",
        geometry_m=LineString([(5.0, 10.0), (35.0, 10.0)]),
        tags={"highway": "pedestrian"},
        osm_id="way/pedestrian",
    )

    footway_mesh = build_road_meshes([footway], scaler, terrain, params)
    pedestrian_mesh = build_road_meshes([pedestrian], scaler, terrain, params)

    assert road_width_mm(footway.tags, scaler, params) == 0.4
    assert road_width_mm(pedestrian.tags, scaler, params) == 0.7
    assert math.isclose(float(np.ptp(footway_mesh.vertices[:, 1])), 0.4, abs_tol=1e-6)
    assert math.isclose(float(np.ptp(pedestrian_mesh.vertices[:, 1])), 0.7, abs_tol=1e-6)


def test_airport_layer_uses_parking_thickness_for_runway_lines():
    params = ModelParams(south=0.0, west=0.0, north=0.01, east=0.01)
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=80.0, height_mm=80.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 80.0], [0.0, 80.0]]),
        y_mm=np.asarray([[0.0, 0.0], [80.0, 80.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    runway = OSMFeature(
        layer="airport",
        geometry_m=LineString([(10.0, 40.0), (70.0, 40.0)]),
        tags={"aeroway": "runway", "width": "20 m"},
        osm_id="way/runway",
    )

    parts = build_surface_layer_meshes([], [], [], [], [runway], [], [], scaler, terrain, params)
    airport = next(part for part in parts if part.name == "airport")

    assert not airport.is_empty()
    assert math.isclose(float(airport.vertices[:, 2].min()), 3.06, abs_tol=1e-6)
    assert math.isclose(float(airport.vertices[:, 2].max()), 3.26, abs_tol=1e-6)


def test_rail_and_subway_layers_generate_optional_parts():
    params = ModelParams(
        south=0.0,
        west=0.0,
        north=0.01,
        east=0.01,
        include_rail_lines=True,
        include_rail_stations=True,
        include_subway_lines=True,
        include_subway_stations=True,
    )
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=80.0, height_mm=80.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 80.0], [0.0, 80.0]]),
        y_mm=np.asarray([[0.0, 0.0], [80.0, 80.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    rail_line = OSMFeature(
        layer="rail_line",
        geometry_m=LineString([(10.0, 20.0), (70.0, 20.0)]),
        tags={"railway": "rail"},
        osm_id="way/rail",
    )
    subway_line = OSMFeature(
        layer="subway_line",
        geometry_m=LineString([(10.0, 30.0), (70.0, 30.0)]),
        tags={"railway": "subway", "tunnel": "yes"},
        osm_id="way/subway",
    )
    rail_station = OSMFeature(
        layer="rail_station",
        geometry_m=Point(20.0, 20.0),
        tags={"railway": "station"},
        osm_id="node/rail-station",
    )
    subway_station = OSMFeature(
        layer="subway_station",
        geometry_m=Point(40.0, 30.0),
        tags={"railway": "station", "station": "subway"},
        osm_id="node/subway-station",
    )

    parts = build_surface_layer_meshes(
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        scaler,
        terrain,
        params,
        rail_line_features=[rail_line],
        rail_station_features=[rail_station],
        subway_line_features=[subway_line],
        subway_station_features=[subway_station],
    )
    by_name = {part.name: part for part in parts}

    assert {"rail_lines", "rail_stations", "subway_lines", "subway_stations"} <= set(by_name)
    assert not by_name["rail_lines"].is_empty()
    assert not by_name["rail_stations"].is_empty()
    assert not by_name["subway_lines"].is_empty()
    assert not by_name["subway_stations"].is_empty()


def test_green_surface_follows_terrain_relief():
    params = ModelParams(south=0.0, west=0.0, north=0.01, east=0.01)
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    xs = np.tile(np.linspace(0.0, 40.0, 5), (5, 1))
    ys = np.tile(np.linspace(0.0, 40.0, 5).reshape(5, 1), (1, 5))
    terrain = TerrainGrid(x_mm=xs, y_mm=ys, z_mm=3.0 + ys * 0.2)
    green_feature = OSMFeature(
        layer="green",
        geometry_m=Polygon([(5.0, 5.0), (35.0, 5.0), (35.0, 35.0), (5.0, 35.0)]),
        tags={"landuse": "grass"},
        osm_id="way/green-slope",
    )

    parts = build_surface_layer_meshes([], [], [green_feature], [], [], [], [], scaler, terrain, params)
    green = next(part for part in parts if part.name == "green")

    assert not green.is_empty()
    assert float(np.ptp(green.vertices[:, 2])) > 5.5


def test_building_bottom_follows_terrain_but_roof_stays_flat():
    params = ModelParams(
        south=0.0,
        west=0.0,
        north=0.01,
        east=0.01,
        default_building_height_m=10.0,
        max_building_height_mm=50.0,
    )
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    xs = np.tile(np.linspace(0.0, 40.0, 5), (5, 1))
    ys = np.tile(np.linspace(0.0, 40.0, 5).reshape(5, 1), (1, 5))
    terrain = TerrainGrid(x_mm=xs, y_mm=ys, z_mm=3.0 + ys * 0.2)
    feature = OSMFeature(
        layer="building",
        geometry_m=Polygon([(5.0, 5.0), (35.0, 5.0), (35.0, 35.0), (5.0, 35.0)]),
        tags={"building": "yes"},
        osm_id="way/slope-building",
    )

    building = build_building_meshes([feature], scaler, terrain, params)
    top_z = float(building.vertices[:, 2].max())
    bottom_z = building.vertices[building.vertices[:, 2] < top_z - 1e-6, 2]

    assert not building.is_empty()
    assert float(np.ptp(bottom_z)) > 5.5
    assert np.allclose(building.vertices[np.isclose(building.vertices[:, 2], top_z), 2], top_z)
    assert top_z < float(bottom_z.max()) + params.default_building_height_m + 1.1
    assert mesh_diagnostics(building)["non_manifold_edges"] == 0


def test_high_detail_building_parts_replace_parent_block():
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=50.0, height_mm=50.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 50.0], [0.0, 50.0]]),
        y_mm=np.asarray([[0.0, 0.0], [50.0, 50.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    parent = OSMFeature(
        layer="building",
        geometry_m=Polygon([(0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0)]),
        tags={"building": "yes", "height": "20"},
        osm_id="way/parent",
    )
    part = OSMFeature(
        layer="building",
        geometry_m=Polygon([(5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0)]),
        tags={"building:part": "yes", "height": "6"},
        osm_id="way/part",
    )

    normal = build_building_meshes(
        [parent, part],
        scaler,
        terrain,
        ModelParams(south=0.0, west=0.0, north=0.01, east=0.01),
    )
    high = build_building_meshes(
        [parent, part],
        scaler,
        terrain,
        ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, model_detail_mode="high"),
    )

    assert float(normal.vertices[:, 2].max()) > 20.0
    assert math.isclose(float(high.vertices[:, 2].max()), 9.0, abs_tol=1e-6)


def test_high_detail_building_part_respects_min_height():
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 40.0], [0.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0], [40.0, 40.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    part = OSMFeature(
        layer="building",
        geometry_m=Polygon([(5.0, 5.0), (20.0, 5.0), (20.0, 20.0), (5.0, 20.0)]),
        tags={"building:part": "yes", "height": "12", "min_height": "4"},
        osm_id="way/elevated-part",
    )

    high = build_building_meshes(
        [part],
        scaler,
        terrain,
        ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, model_detail_mode="high"),
    )

    assert math.isclose(float(high.vertices[:, 2].min()), 7.0, abs_tol=1e-6)
    assert math.isclose(float(high.vertices[:, 2].max()), 15.0, abs_tol=1e-6)


def test_high_detail_monument_uses_stepped_landmark_shape():
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=50.0, height_mm=50.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 50.0], [0.0, 50.0]]),
        y_mm=np.asarray([[0.0, 0.0], [50.0, 50.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    monument = OSMFeature(
        layer="building",
        geometry_m=Polygon([(0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0)]),
        tags={"building": "yes", "historic": "monument", "memorial": "stele", "height": "20"},
        osm_id="relation/monument",
    )

    high = build_building_meshes(
        [monument],
        scaler,
        terrain,
        ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, model_detail_mode="high"),
    )
    top_z = float(high.vertices[:, 2].max())
    top_xy = high.vertices[np.isclose(high.vertices[:, 2], top_z), :2]
    z_levels = np.unique(np.round(high.vertices[:, 2], 6))

    assert not high.is_empty()
    assert float(np.ptp(top_xy[:, 0])) < 12.0
    assert float(np.ptp(top_xy[:, 1])) < 12.0
    assert len(z_levels) >= 5


def test_high_detail_uses_osm_gabled_roof_shape():
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 40.0], [0.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0], [40.0, 40.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    feature = OSMFeature(
        layer="building",
        geometry_m=Polygon([(5.0, 8.0), (35.0, 8.0), (35.0, 24.0), (5.0, 24.0)]),
        tags={"building": "yes", "height": "12", "roof:shape": "gabled", "roof:height": "4"},
        osm_id="way/gabled",
    )

    normal = build_building_meshes(
        [feature],
        scaler,
        terrain,
        ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, model_detail_mode="normal"),
    )
    high = build_building_meshes(
        [feature],
        scaler,
        terrain,
        ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, model_detail_mode="high"),
    )
    normal_top_z = float(normal.vertices[:, 2].max())
    high_top_z = float(high.vertices[:, 2].max())
    high_upper_vertices = high.vertices[high.vertices[:, 2] > high_top_z - 4.2]

    assert math.isclose(normal_top_z, 15.0, abs_tol=1e-6)
    assert math.isclose(high_top_z, 15.0, abs_tol=1e-6)
    assert len(np.unique(np.round(high_upper_vertices[:, 2], 6))) >= 2
    assert len(np.unique(np.round(normal.vertices[:, 2], 6))) == 2
    diagnostics = mesh_diagnostics(high)
    assert diagnostics["watertight"] is True
    assert diagnostics["non_manifold_edges"] == 0


def test_osm_roof_meshes_use_only_exterior_sides():
    poly = Polygon([(0.0, 0.0), (30.0, 0.0), (30.0, 16.0), (0.0, 16.0)])

    for shape in ("gabled", "hipped", "pyramidal", "skillion", "dome"):
        roof = build_osm_roof_mesh(poly, 8.0, 12.0, shape, "building", COLORS["buildings"])
        diagnostics = mesh_diagnostics(roof)

        assert not roof.is_empty()
        assert diagnostics["watertight"] is True
        assert diagnostics["non_manifold_edges"] == 0


def test_high_detail_skillion_roof_uses_osm_direction_on_quad_parts():
    poly = Polygon([(0.0, 0.0), (22.0, 0.0), (18.0, 3.0), (2.0, 5.0)])

    roof = build_osm_roof_mesh(
        poly,
        8.0,
        12.0,
        "skillion",
        "building",
        COLORS["buildings"],
        tags={"roof:direction": "0"},
    )
    diagnostics = mesh_diagnostics(roof)
    north_vertices = roof.vertices[roof.vertices[:, 1] > 4.9]
    south_vertices = roof.vertices[roof.vertices[:, 1] < 0.1]

    assert not roof.is_empty()
    assert diagnostics["watertight"] is True
    assert diagnostics["non_manifold_edges"] == 0
    assert math.isclose(float(north_vertices[:, 2].max()), 12.0, abs_tol=1e-6)
    assert float(south_vertices[:, 2].max()) < 12.0


def test_high_detail_flattens_skillion_building_parts_for_printable_cuboids():
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=30.0, height_mm=30.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 30.0], [0.0, 30.0]]),
        y_mm=np.asarray([[0.0, 0.0], [30.0, 30.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    feature = OSMFeature(
        layer="building",
        geometry_m=Polygon([(0.0, 0.0), (22.0, 0.0), (18.0, 3.0), (2.0, 5.0)]),
        tags={"building:part": "yes", "height": "12", "roof:shape": "skillion", "roof:height": "4", "roof:direction": "0"},
        osm_id="way/skillion-direction",
    )

    high = build_building_meshes(
        [feature],
        scaler,
        terrain,
        ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, model_detail_mode="high"),
    )
    z_levels = np.unique(np.round(high.vertices[:, 2], 6))

    assert math.isclose(float(high.vertices[:, 2].max()), 15.0, abs_tol=1e-6)
    assert set(np.round(z_levels, 6)) == {3.0, 15.0}
    diagnostics = mesh_diagnostics(high)
    assert diagnostics["watertight"] is True
    assert diagnostics["non_manifold_edges"] == 0


def test_high_detail_roof_only_building_part_is_closed():
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 40.0], [0.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0], [40.0, 40.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    roof_part = OSMFeature(
        layer="building",
        geometry_m=Polygon([(5.0, 8.0), (35.0, 8.0), (35.0, 24.0), (5.0, 24.0)]),
        tags={
            "building:part": "yes",
            "height": "35",
            "min_height": "29",
            "roof:shape": "gabled",
            "roof:height": "6",
        },
        osm_id="way/roof-only-part",
    )

    high = build_building_meshes(
        [roof_part],
        scaler,
        terrain,
        ModelParams(
            south=0.0,
            west=0.0,
            north=0.01,
            east=0.01,
            model_detail_mode="high",
            max_building_height_mm=100.0,
        ),
    )
    diagnostics = mesh_diagnostics(high)

    assert not high.is_empty()
    assert diagnostics["watertight"] is True
    assert diagnostics["non_manifold_edges"] == 0


def test_high_detail_uses_osm_dome_roof_shape():
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=50.0, height_mm=50.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 50.0], [0.0, 50.0]]),
        y_mm=np.asarray([[0.0, 0.0], [50.0, 50.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    feature = OSMFeature(
        layer="building",
        geometry_m=Point(25.0, 25.0).buffer(15.0, quad_segs=16),
        tags={"building": "yes", "height": "14", "roof:shape": "dome", "roof:height": "6"},
        osm_id="way/dome",
    )

    high = build_building_meshes(
        [feature],
        scaler,
        terrain,
        ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, model_detail_mode="high"),
    )
    z_levels = np.unique(np.round(high.vertices[:, 2], 3))

    assert not high.is_empty()
    assert math.isclose(float(high.vertices[:, 2].max()), 17.0, abs_tol=1e-6)
    assert len(z_levels) >= 30
    diagnostics = mesh_diagnostics(high)
    assert diagnostics["watertight"] is True
    assert diagnostics["non_manifold_edges"] == 0
    assert diagnostics["triangles"] > 6000


def _top_surface(part):
    top_z = float(part.vertices[:, 2].max())
    top_tris = []
    for face in part.faces:
        tri = part.vertices[face]
        if np.allclose(tri[:, 2], top_z):
            top_tris.append(Polygon([(float(x), float(y)) for x, y, _ in tri]))
    return top_z, unary_union(top_tris)


def test_area_infill_empty_area_mode_skips_whole_polygons_with_buildings():
    params = ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, area_infill_height_mm=0.40)
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=60.0, height_mm=60.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 60.0], [0.0, 60.0]]),
        y_mm=np.asarray([[0.0, 0.0], [60.0, 60.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    occupied_area = OSMFeature(
        layer="area_infill",
        geometry_m=Polygon([(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]),
        tags={"landuse": "residential"},
        osm_id="way/occupied-area",
    )
    empty_area = OSMFeature(
        layer="area_infill",
        geometry_m=Polygon([(30.0, 30.0), (50.0, 30.0), (50.0, 50.0), (30.0, 50.0)]),
        tags={"landuse": "industrial"},
        osm_id="way/empty-area",
    )
    building = OSMFeature(
        layer="building",
        geometry_m=Polygon([(8.0, 8.0), (14.0, 8.0), (14.0, 14.0), (8.0, 14.0)]),
        tags={"building": "yes"},
        osm_id="way/building",
    )

    parts = build_surface_layer_meshes(
        [],
        [],
        [],
        [],
        [],
        [occupied_area, empty_area],
        [building],
        scaler,
        terrain,
        params,
    )
    area_part = next(part for part in parts if part.name == "area_infill")
    top_z, top_surface = _top_surface(area_part)

    assert math.isclose(top_z, 3.47, abs_tol=1e-6)
    assert not top_surface.covers(Point(2.0, 2.0))
    assert not top_surface.covers(Point(11.0, 11.0))
    assert top_surface.covers(Point(40.0, 40.0))


def test_area_infill_all_area_mode_generates_whole_polygons_even_with_buildings():
    params = ModelParams(
        south=0.0,
        west=0.0,
        north=0.01,
        east=0.01,
        area_infill_height_mm=0.40,
        area_infill_mode="all_areas",
    )
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=60.0, height_mm=60.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 60.0], [0.0, 60.0]]),
        y_mm=np.asarray([[0.0, 0.0], [60.0, 60.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    area = OSMFeature(
        layer="area_infill",
        geometry_m=Polygon([(0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0)]),
        tags={"landuse": "residential"},
        osm_id="way/area",
    )
    building = OSMFeature(
        layer="building",
        geometry_m=Polygon([(8.0, 8.0), (14.0, 8.0), (14.0, 14.0), (8.0, 14.0)]),
        tags={"building": "yes"},
        osm_id="way/building",
    )

    parts = build_surface_layer_meshes([], [], [], [], [], [area], [building], scaler, terrain, params)
    area_part = next(part for part in parts if part.name == "area_infill")
    _, top_surface = _top_surface(area_part)

    assert top_surface.covers(Point(2.0, 2.0))
    assert top_surface.covers(Point(11.0, 11.0))


def test_area_infill_all_area_mode_skips_large_parent_that_covers_details():
    params = ModelParams(
        south=0.0,
        west=0.0,
        north=0.02,
        east=0.02,
        area_infill_height_mm=0.40,
        area_infill_mode="all_areas",
    )
    scaler = ModelScaler(scale_mm_per_m=0.12, width_mm=180.0, height_mm=180.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 180.0], [0.0, 180.0]]),
        y_mm=np.asarray([[0.0, 0.0], [180.0, 180.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    broad_parent = OSMFeature(
        layer="area_infill",
        geometry_m=Polygon([(0.0, 0.0), (1500.0, 0.0), (1500.0, 1500.0), (0.0, 1500.0)]),
        tags={"landuse": "commercial", "name": "Large parent district"},
        osm_id="way/large-parent",
    )
    small_area = OSMFeature(
        layer="area_infill",
        geometry_m=Polygon([(100.0, 100.0), (240.0, 100.0), (240.0, 240.0), (100.0, 240.0)]),
        tags={"amenity": "hospital"},
        osm_id="way/small-specific-area",
    )
    detail_building = OSMFeature(
        layer="building",
        geometry_m=Polygon([(420.0, 420.0), (980.0, 420.0), (980.0, 980.0), (420.0, 980.0)]),
        tags={"building": "yes"},
        osm_id="way/detail-building",
    )
    primary_road = OSMFeature(
        layer="road",
        geometry_m=LineString([(0.0, 760.0), (1500.0, 760.0)]),
        tags={"highway": "primary", "width": "20 m"},
        osm_id="way/main-road",
    )

    parts = build_surface_layer_meshes(
        [primary_road],
        [],
        [],
        [],
        [],
        [broad_parent, small_area],
        [detail_building],
        scaler,
        terrain,
        params,
    )
    area_part = next(part for part in parts if part.name == "area_infill")
    _, top_surface = _top_surface(area_part)

    assert top_surface.covers(Point(20.0, 20.0))
    assert not top_surface.covers(Point(120.0, 120.0))


def test_road_line_densifies_over_terrain_peak():
    params = ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, min_road_width_mm=0.1)
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 20.0, 40.0], [0.0, 20.0, 40.0], [0.0, 20.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0, 0.0], [20.0, 20.0, 20.0], [40.0, 40.0, 40.0]]),
        z_mm=np.asarray([[3.0, 3.0, 3.0], [3.0, 12.0, 3.0], [3.0, 3.0, 3.0]]),
    )
    road = OSMFeature(
        layer="road",
        geometry_m=LineString([(2.0, 20.0), (38.0, 20.0)]),
        tags={"highway": "residential", "width": "2 m"},
        osm_id="way/terrain-peak",
    )

    mesh = build_road_meshes([road], scaler, terrain, params)

    assert not mesh.is_empty()
    assert float(mesh.vertices[:, 2].max()) > 10.0


def test_route_line_follows_terrain_peak():
    params = ModelParams(
        south=0.0,
        west=0.0,
        north=0.01,
        east=0.01,
        include_route=True,
        route_segments=[[[0.001, 0.001], [0.009, 0.009]]],
        route_width_mm=0.8,
        route_height_mm=0.6,
    )
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 20.0, 40.0], [0.0, 20.0, 40.0], [0.0, 20.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0, 0.0], [20.0, 20.0, 20.0], [40.0, 40.0, 40.0]]),
        z_mm=np.asarray([[3.0, 3.0, 3.0], [3.0, 12.0, 3.0], [3.0, 3.0, 3.0]]),
    )
    route_line = LineString([(2.0, 2.0), (38.0, 38.0)])

    mesh = build_route_meshes([route_line], scaler, terrain, params)

    assert not mesh.is_empty()
    assert mesh.name == "route"
    assert float(np.ptp(mesh.vertices[:, 2])) > 4.0


def test_concave_surface_extrusion_does_not_fill_outside_notch():
    poly = Polygon([(0, 0), (5, 0), (5, 2), (2, 2), (2, 5), (0, 5), (0, 0)])

    mesh = extrude_polygon(poly, 0.0, 1.0, "concave", (1, 2, 3, 255))
    top_tris = []
    for face in mesh.faces:
        tri = mesh.vertices[face]
        if np.allclose(tri[:, 2], 1.0):
            top_tris.append(Polygon([(float(x), float(y)) for x, y, _ in tri]))
    top_surface = unary_union(top_tris)

    assert poly.difference(top_surface).area < 1e-6
    assert top_surface.difference(poly).area < 1e-6
    assert not top_surface.covers(Point(4.0, 4.0))


def test_roundabout_mesh_keeps_center_island_open():
    params = ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, min_road_width_mm=0.1)
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 40.0], [0.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0], [40.0, 40.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    cx, cy, radius = 20.0, 20.0, 5.0
    coords = [
        (cx + math.cos(i * math.tau / 48) * radius, cy + math.sin(i * math.tau / 48) * radius)
        for i in range(48)
    ]
    coords.append(coords[0])
    feature = OSMFeature(
        layer="road",
        geometry_m=LineString(coords),
        tags={"highway": "tertiary", "junction": "roundabout", "width": "15'0\""},
        osm_id="way/roundabout",
    )

    mesh = build_road_meshes([feature], scaler, terrain, params)
    top_z = float(mesh.vertices[:, 2].max())
    top_tris = []
    for face in mesh.faces:
        tri = mesh.vertices[face]
        if np.allclose(tri[:, 2], top_z):
            top_tris.append(Polygon([(float(x), float(y)) for x, y, _ in tri]))

    top_surface = unary_union(top_tris)

    assert top_surface.area > 0
    assert not top_surface.covers(Point(cx, cy))


def test_bridge_tag_without_water_cutout_stays_on_terrain():
    params = ModelParams(
        south=0.0,
        west=0.0,
        north=0.01,
        east=0.01,
        min_road_width_mm=0.1,
        bridge_clearance_mm=2.5,
    )
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 40.0], [0.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0], [40.0, 40.0]]),
        z_mm=np.asarray([[6.0, 6.0], [3.0, 3.0]]),
    )
    coords = [(5.0, 5.0), (20.0, 20.0), (35.0, 5.0)]
    feature = OSMFeature(
        layer="road",
        geometry_m=LineString(coords),
        tags={"highway": "residential", "bridge": "yes"},
        osm_id="way/bridge",
    )

    mesh = build_road_meshes([feature], scaler, terrain, params)
    non_bridge = OSMFeature(
        layer="road",
        geometry_m=LineString(coords),
        tags={"highway": "residential"},
        osm_id="way/plain-road",
    )
    plain_mesh = build_road_meshes([non_bridge], scaler, terrain, params)

    assert not mesh.is_empty()
    assert np.allclose(np.sort(mesh.vertices[:, 2]), np.sort(plain_mesh.vertices[:, 2]))


def test_road_segment_samples_corner_terrain():
    params = ModelParams(south=0.0, west=0.0, north=0.01, east=0.01, min_road_width_mm=0.1)
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 40.0], [0.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0], [40.0, 40.0]]),
        z_mm=np.asarray([[3.0, 3.0], [9.0, 9.0]]),
    )
    feature = OSMFeature(
        layer="road",
        geometry_m=LineString([(10.0, 5.0), (10.0, 35.0)]),
        tags={"highway": "residential", "width": "2 m"},
        osm_id="way/slope-road",
    )

    mesh = build_road_meshes([feature], scaler, terrain, params)

    assert not mesh.is_empty()
    assert float(np.ptp(mesh.vertices[:, 2])) > 4.0


def test_positive_layer_counts_as_bridge_but_bridge_no_does_not():
    assert is_bridge({"highway": "primary", "layer": "1"})
    assert is_bridge({"highway": "primary", "bridge": "viaduct"})
    assert not is_bridge({"highway": "primary", "bridge": "no", "layer": "0"})


def test_water_cutout_road_crossing_is_elevated_like_bridge():
    params = ModelParams(
        south=0.0,
        west=0.0,
        north=0.01,
        east=0.01,
        min_road_width_mm=0.1,
        bridge_clearance_mm=2.5,
        cut_out_water=True,
    )
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 40.0], [0.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0], [40.0, 40.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    water = Polygon([(12.0, 10.0), (28.0, 10.0), (28.0, 30.0), (12.0, 30.0)])
    feature = OSMFeature(
        layer="road",
        geometry_m=LineString([(5.0, 20.0), (35.0, 20.0)]),
        tags={"highway": "residential"},
        osm_id="way/water-crossing",
    )

    mesh = build_road_meshes([feature], scaler, terrain, params, water_union_m=water)

    assert not mesh.is_empty()
    assert float(mesh.vertices[:, 2].min()) >= 3.0 + 0.12 + 2.5 - 1e-6


def test_tunnel_crossing_water_cutout_is_not_auto_elevated():
    params = ModelParams(
        south=0.0,
        west=0.0,
        north=0.01,
        east=0.01,
        min_road_width_mm=0.1,
        bridge_clearance_mm=2.5,
        cut_out_water=True,
    )
    scaler = ModelScaler(scale_mm_per_m=1.0, width_mm=40.0, height_mm=40.0)
    terrain = TerrainGrid(
        x_mm=np.asarray([[0.0, 40.0], [0.0, 40.0]]),
        y_mm=np.asarray([[0.0, 0.0], [40.0, 40.0]]),
        z_mm=np.full((2, 2), 3.0),
    )
    water = Polygon([(12.0, 10.0), (28.0, 10.0), (28.0, 30.0), (12.0, 30.0)])
    feature = OSMFeature(
        layer="road",
        geometry_m=LineString([(5.0, 20.0), (35.0, 20.0)]),
        tags={"highway": "residential", "tunnel": "yes"},
        osm_id="way/tunnel",
    )

    mesh = build_road_meshes([feature], scaler, terrain, params, water_union_m=water)

    assert not mesh.is_empty()
    assert math.isclose(float(mesh.vertices[:, 2].min()), 3.0 + 0.12, abs_tol=1e-6)


def test_terrain_cutout_removes_top_and_bottom_faces():
    xs = np.tile(np.arange(5, dtype=float), (5, 1))
    ys = np.tile(np.arange(5, dtype=float).reshape(5, 1), (1, 5))
    terrain = TerrainGrid(x_mm=xs, y_mm=ys, z_mm=np.full((5, 5), 3.0))
    cutout = Polygon([(1.25, 1.25), (2.75, 1.25), (2.75, 2.75), (1.25, 2.75)])

    mesh = terrain_to_mesh(terrain, cutouts_mm=[cutout])
    top_tris = []
    bottom_tris = []
    for face in mesh.faces:
        tri = mesh.vertices[face]
        poly = Polygon([(float(x), float(y)) for x, y, _ in tri])
        if np.allclose(tri[:, 2], 3.0):
            top_tris.append(poly)
        elif np.allclose(tri[:, 2], 0.0):
            bottom_tris.append(poly)

    top_surface = unary_union(top_tris)
    bottom_surface = unary_union(bottom_tris)

    assert top_surface.covers(Point(0.5, 0.5))
    assert bottom_surface.covers(Point(0.5, 0.5))
    assert not top_surface.covers(Point(2.0, 2.0))
    assert not bottom_surface.covers(Point(2.0, 2.0))


def test_terrain_footprint_clips_outer_cells():
    xs = np.tile(np.arange(5, dtype=float), (5, 1))
    ys = np.tile(np.arange(5, dtype=float).reshape(5, 1), (1, 5))
    terrain = TerrainGrid(x_mm=xs, y_mm=ys, z_mm=np.full((5, 5), 3.0))
    footprint = Point(2.0, 2.0).buffer(1.2, quad_segs=32)

    mesh = terrain_to_mesh(terrain, footprint_mm=footprint)
    top_tris = []
    for face in mesh.faces:
        tri = mesh.vertices[face]
        poly = Polygon([(float(x), float(y)) for x, y, _ in tri])
        if np.allclose(tri[:, 2], 3.0):
            top_tris.append(poly)

    top_surface = unary_union(top_tris)

    assert top_surface.covers(Point(2.0, 2.0))
    assert not top_surface.covers(Point(0.5, 0.5))
