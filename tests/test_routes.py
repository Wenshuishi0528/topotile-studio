from shapely.geometry import Polygon

from city_modeler.geo import make_local_projection
from city_modeler.routes import parse_route_text, route_point_count, route_segments_to_local_lines


def test_parse_gpx_track_segments():
    gpx = """<?xml version="1.0"?>
    <gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
      <trk><trkseg>
        <trkpt lat="47.6200" lon="-122.3500" />
        <trkpt lat="47.6210" lon="-122.3490" />
        <trkpt lat="47.6220" lon="-122.3480" />
      </trkseg></trk>
    </gpx>"""

    segments = parse_route_text(gpx, "track.gpx")

    assert len(segments) == 1
    assert route_point_count(segments) == 3
    assert segments[0][0] == [47.62, -122.35]


def test_parse_kml_line_coordinates():
    kml = """<?xml version="1.0"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document><Placemark><LineString><coordinates>
        -122.3500,47.6200,0 -122.3490,47.6210,0 -122.3480,47.6220,0
      </coordinates></LineString></Placemark></Document>
    </kml>"""

    segments = parse_route_text(kml, "track.kml")

    assert len(segments) == 1
    assert route_point_count(segments) == 3
    assert segments[0][-1] == [47.622, -122.348]


def test_route_segments_clip_to_local_footprint():
    projection = make_local_projection(47.6200, -122.3500, 47.6230, -122.3470)
    segments = [[
        [47.6190, -122.3510],
        [47.6210, -122.3490],
        [47.6240, -122.3460],
    ]]
    clip = Polygon([(0.0, 0.0), (projection.width_m, 0.0), (projection.width_m, projection.height_m), (0.0, projection.height_m)])

    lines = route_segments_to_local_lines(segments, projection, clip)

    assert lines
    assert all(line.length > 0 for line in lines)
