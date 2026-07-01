from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from shapely.geometry import GeometryCollection, LineString
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from .geo import LocalProjection
from .params import normalize_route_segments


RouteSegments = list[list[list[float]]]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _children_named(node: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(node) if _local_name(child.tag) == name]


def _iter_named(node: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in node.iter() if _local_name(item.tag) == name]


def _parse_point_attrs(node: ET.Element) -> list[float] | None:
    try:
        lat = float(node.attrib["lat"])
        lon = float(node.attrib["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return [lat, lon]


def _parse_gpx(root: ET.Element) -> RouteSegments:
    segments: RouteSegments = []
    for trkseg in _iter_named(root, "trkseg"):
        segment = []
        for trkpt in _children_named(trkseg, "trkpt"):
            point = _parse_point_attrs(trkpt)
            if point is not None:
                segment.append(point)
        if len(segment) >= 2:
            segments.append(segment)

    for route in _iter_named(root, "rte"):
        segment = []
        for rtept in _children_named(route, "rtept"):
            point = _parse_point_attrs(rtept)
            if point is not None:
                segment.append(point)
        if len(segment) >= 2:
            segments.append(segment)

    if not segments:
        segment = []
        for trkpt in _iter_named(root, "trkpt"):
            point = _parse_point_attrs(trkpt)
            if point is not None:
                segment.append(point)
        if len(segment) >= 2:
            segments.append(segment)
    return normalize_route_segments(segments)


def _parse_kml_coordinates(text: str | None) -> list[list[float]]:
    if not text:
        return []
    points: list[list[float]] = []
    for token in text.replace("\n", " ").replace("\t", " ").split():
        fields = token.split(",")
        if len(fields) < 2:
            continue
        try:
            lon = float(fields[0])
            lat = float(fields[1])
        except ValueError:
            continue
        points.append([lat, lon])
    return points


def _parse_kml(root: ET.Element) -> RouteSegments:
    segments = []
    for coordinates in _iter_named(root, "coordinates"):
        segment = _parse_kml_coordinates(coordinates.text)
        if len(segment) >= 2:
            segments.append(segment)
    return normalize_route_segments(segments)


def parse_route_text(text: str, filename: str = "") -> RouteSegments:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"Route file is not valid XML: {exc}") from exc

    suffix = Path(filename).suffix.lower()
    root_name = _local_name(root.tag)
    if suffix == ".kml" or root_name == "kml":
        segments = _parse_kml(root)
    elif suffix == ".gpx" or root_name == "gpx":
        segments = _parse_gpx(root)
    else:
        segments = _parse_gpx(root) or _parse_kml(root)

    if not segments:
        raise ValueError("Route file did not contain at least two GPX/KML coordinates.")
    return segments


def parse_route_file(path: str | Path) -> RouteSegments:
    path = Path(path)
    return parse_route_text(path.read_text(encoding="utf-8"), path.name)


def route_point_count(segments: RouteSegments) -> int:
    return sum(len(segment) for segment in segments)


def _iter_lines(geom: BaseGeometry):
    if geom.is_empty:
        return
    if isinstance(geom, LineString):
        yield geom
    elif isinstance(geom, GeometryCollection):
        for child in geom.geoms:
            yield from _iter_lines(child)
    else:
        geoms = getattr(geom, "geoms", None)
        if geoms is not None:
            for child in geoms:
                yield from _iter_lines(child)


def route_segments_to_local_lines(
    segments: RouteSegments,
    projection: LocalProjection,
    clip_m: BaseGeometry | None = None,
) -> list[LineString]:
    lines: list[LineString] = []
    for segment in normalize_route_segments(segments):
        coords = [projection.lonlat_to_local(lon, lat) for lat, lon in segment]
        if len(coords) < 2:
            continue
        line = LineString(coords)
        if line.is_empty or line.length <= 0:
            continue
        if clip_m is not None and not clip_m.is_empty:
            try:
                clipped = line.intersection(clip_m)
            except Exception:
                continue
            if not clipped.is_valid:
                clipped = make_valid(clipped)
            for piece in _iter_lines(clipped):
                if piece.length > 0:
                    lines.append(piece)
        else:
            lines.append(line)
    return lines
