from __future__ import annotations

from dataclasses import dataclass
from pyproj import CRS, Transformer
from shapely.geometry import Polygon


def utm_epsg_for_lonlat(lon: float, lat: float) -> int:
    zone = int((lon + 180.0) // 6.0) + 1
    zone = max(1, min(zone, 60))
    return (32600 if lat >= 0 else 32700) + zone


@dataclass(slots=True)
class LocalProjection:
    epsg: int
    origin_x: float
    origin_y: float
    width_m: float
    height_m: float
    transformer_to_local_crs: Transformer
    transformer_to_wgs84_crs: Transformer

    def lonlat_to_local(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = self.transformer_to_local_crs.transform(lon, lat)
        return x - self.origin_x, y - self.origin_y

    def local_to_lonlat(self, x_m: float, y_m: float) -> tuple[float, float]:
        lon, lat = self.transformer_to_wgs84_crs.transform(x_m + self.origin_x, y_m + self.origin_y)
        return lon, lat

    @property
    def bbox_polygon_m(self) -> Polygon:
        return Polygon([(0, 0), (self.width_m, 0), (self.width_m, self.height_m), (0, self.height_m)])


def make_local_projection(south: float, west: float, north: float, east: float) -> LocalProjection:
    center_lon = (west + east) / 2.0
    center_lat = (south + north) / 2.0
    epsg = utm_epsg_for_lonlat(center_lon, center_lat)
    crs = CRS.from_epsg(epsg)
    to_local = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    corners = [
        to_local.transform(west, south),
        to_local.transform(east, south),
        to_local.transform(east, north),
        to_local.transform(west, north),
    ]
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    origin_x = min(xs)
    origin_y = min(ys)
    width_m = max(xs) - origin_x
    height_m = max(ys) - origin_y
    return LocalProjection(epsg, origin_x, origin_y, width_m, height_m, to_local, to_wgs84)


@dataclass(slots=True)
class ModelScaler:
    scale_mm_per_m: float
    width_mm: float
    height_mm: float

    def xy_to_mm(self, x_m: float, y_m: float) -> tuple[float, float]:
        return x_m * self.scale_mm_per_m, y_m * self.scale_mm_per_m

    def length_m_to_mm(self, length_m: float) -> float:
        return length_m * self.scale_mm_per_m

    def length_mm_to_m(self, length_mm: float) -> float:
        return length_mm / self.scale_mm_per_m


def make_scaler(width_m: float, height_m: float, max_size_mm: float) -> ModelScaler:
    max_m = max(width_m, height_m)
    if max_m <= 0:
        raise ValueError("Selected area has zero size after projection.")
    scale = max_size_mm / max_m
    return ModelScaler(scale, width_m * scale, height_m * scale)
