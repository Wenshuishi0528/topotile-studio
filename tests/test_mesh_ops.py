import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from city_modeler.dem import TerrainGrid
from city_modeler.geo import ModelScaler
from city_modeler.mesh_ops import build_road_meshes, build_surface_layer_meshes, extrude_polygon, is_bridge, road_width_m, road_width_mm, terrain_to_mesh
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

    parts = build_surface_layer_meshes([], [], [], [], [runway], scaler, terrain, params)
    airport = next(part for part in parts if part.name == "airport")

    assert not airport.is_empty()
    assert math.isclose(float(airport.vertices[:, 2].min()), 3.06, abs_tol=1e-6)
    assert math.isclose(float(airport.vertices[:, 2].max()), 3.26, abs_tol=1e-6)


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

    parts = build_surface_layer_meshes([], [], [green_feature], [], [], scaler, terrain, params)
    green = next(part for part in parts if part.name == "green")

    assert not green.is_empty()
    assert float(np.ptp(green.vertices[:, 2])) > 5.5


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
