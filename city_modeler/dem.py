from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import numpy as np
from pyproj import Transformer
import requests

from .geo import LocalProjection, ModelScaler
from .params import ModelParams

OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
TERRAIN_TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/geotiff/{z}/{x}/{y}.tif"
TERRAIN_TILE_CACHE = Path(__file__).resolve().parents[1] / "data" / "cache" / "terrain_tiles"
AUTO_ELEVATION_MAX_GRID_SIZE = 48
AUTO_ELEVATION_ATTRIBUTION = (
    "Elevation data: Copernicus DEM GLO-90 via Open-Meteo Elevation API. "
    "Copernicus DEM DOI: https://doi.org/10.5270/ESA-c5d3d65. "
    "Open-Meteo: https://open-meteo.com/"
)
TERRAIN_TILE_ATTRIBUTION = (
    "Elevation data: Mapzen/Amazon Web Services Terrain Tiles, derived from open elevation datasets "
    "including USGS/NED, SRTM, GMTED, ETOPO1, and other regional sources."
)


@dataclass(slots=True)
class TerrainGrid:
    x_mm: np.ndarray
    y_mm: np.ndarray
    z_mm: np.ndarray

    @property
    def nx(self) -> int:
        return int(self.x_mm.shape[1])

    @property
    def ny(self) -> int:
        return int(self.x_mm.shape[0])

    def sample_z(self, x_mm: float, y_mm: float) -> float:
        xs = self.x_mm[0, :]
        ys = self.y_mm[:, 0]
        if len(xs) == 1 or len(ys) == 1:
            return float(np.nanmean(self.z_mm))
        x = float(np.clip(x_mm, xs[0], xs[-1]))
        y = float(np.clip(y_mm, ys[0], ys[-1]))
        ix = int(np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2))
        iy = int(np.clip(np.searchsorted(ys, y) - 1, 0, len(ys) - 2))
        x0, x1 = xs[ix], xs[ix + 1]
        y0, y1 = ys[iy], ys[iy + 1]
        tx = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
        ty = 0.0 if y1 == y0 else (y - y0) / (y1 - y0)
        z00 = self.z_mm[iy, ix]
        z10 = self.z_mm[iy, ix + 1]
        z01 = self.z_mm[iy + 1, ix]
        z11 = self.z_mm[iy + 1, ix + 1]
        z0 = z00 * (1 - tx) + z10 * tx
        z1 = z01 * (1 - tx) + z11 * tx
        return float(z0 * (1 - ty) + z1 * ty)


def _grid_shape(width_m: float, height_m: float, max_cells: int) -> tuple[int, int]:
    if width_m >= height_m:
        nx = max_cells
        ny = max(2, int(round(max_cells * height_m / width_m)))
    else:
        ny = max_cells
        nx = max(2, int(round(max_cells * width_m / height_m)))
    return max(2, nx), max(2, ny)


def _terrain_grid_points(
    projection: LocalProjection,
    scaler: ModelScaler,
    max_cells: int,
) -> tuple[np.ndarray, np.ndarray, list[tuple[float, float]]]:
    nx, ny = _grid_shape(projection.width_m, projection.height_m, max_cells)
    xs_m = np.linspace(0, projection.width_m, nx)
    ys_m = np.linspace(0, projection.height_m, ny)
    xx_m, yy_m = np.meshgrid(xs_m, ys_m)
    lonlat = [projection.local_to_lonlat(float(x), float(y)) for x, y in zip(xx_m.ravel(), yy_m.ravel())]
    return xx_m, yy_m, lonlat


def _terrain_from_elevation(
    elev: np.ndarray,
    xx_m: np.ndarray,
    yy_m: np.ndarray,
    scaler: ModelScaler,
    params: ModelParams,
) -> TerrainGrid | None:
    if np.all(~np.isfinite(elev)):
        return None

    median = float(np.nanmedian(elev))
    elev = np.where(np.isfinite(elev), elev, median)
    elev = elev - float(np.nanmin(elev))
    z_rel = elev * scaler.scale_mm_per_m * params.vertical_exaggeration
    max_z = float(np.max(z_rel)) if z_rel.size else 0.0
    if max_z > params.max_terrain_height_mm > 0:
        z_rel = z_rel * (params.max_terrain_height_mm / max_z)
    z_mm = params.base_thickness_mm + z_rel
    return TerrainGrid(x_mm=xx_m * scaler.scale_mm_per_m, y_mm=yy_m * scaler.scale_mm_per_m, z_mm=z_mm)


def make_flat_terrain(projection: LocalProjection, scaler: ModelScaler, params: ModelParams) -> TerrainGrid:
    if params.cut_out_water or params.selection_shape != "rectangle":
        nx, ny = _grid_shape(projection.width_m, projection.height_m, params.terrain_grid_size)
    else:
        nx, ny = 2, 2
    xs_m = np.linspace(0, projection.width_m, nx)
    ys_m = np.linspace(0, projection.height_m, ny)
    xx_m, yy_m = np.meshgrid(xs_m, ys_m)
    x_mm = xx_m * scaler.scale_mm_per_m
    y_mm = yy_m * scaler.scale_mm_per_m
    z_mm = np.full_like(x_mm, params.base_thickness_mm, dtype=float)
    return TerrainGrid(x_mm=x_mm, y_mm=y_mm, z_mm=z_mm)


def make_dem_terrain(dem_path: str | Path | None, projection: LocalProjection, scaler: ModelScaler, params: ModelParams) -> TerrainGrid:
    if not dem_path:
        return make_flat_terrain(projection, scaler, params)

    try:
        import rasterio
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("rasterio is required for DEM GeoTIFF support") from exc

    dem_path = Path(dem_path)
    if not dem_path.exists():
        raise FileNotFoundError(f"DEM file does not exist: {dem_path}")

    xx_m, yy_m, lonlat = _terrain_grid_points(projection, scaler, params.terrain_grid_size)

    with rasterio.open(dem_path) as src:
        src_crs = src.crs or "EPSG:4326"
        to_dem = Transformer.from_crs("EPSG:4326", src_crs, always_xy=True)
        sample_points = [to_dem.transform(lon, lat) for lon, lat in lonlat]
        values = []
        for sample in src.sample(sample_points):
            value = float(sample[0])
            if src.nodata is not None and abs(value - float(src.nodata)) < 1e-9:
                value = np.nan
            if not np.isfinite(value):
                value = np.nan
            values.append(value)

    elev = np.array(values, dtype=float).reshape(xx_m.shape)
    terrain = _terrain_from_elevation(elev, xx_m, yy_m, scaler, params)
    if terrain is None:
        return make_flat_terrain(projection, scaler, params)
    return terrain


def _chunks(items: list[tuple[float, float]], size: int) -> list[list[tuple[float, float]]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def fetch_open_meteo_elevations(lonlat: list[tuple[float, float]]) -> list[float]:
    elevations: list[float] = []
    for chunk in _chunks(lonlat, 100):
        latitudes = ",".join(f"{lat:.6f}" for _, lat in chunk)
        longitudes = ",".join(f"{lon:.6f}" for lon, _ in chunk)
        try:
            response = requests.get(
                OPEN_METEO_ELEVATION_URL,
                params={"latitude": latitudes, "longitude": longitudes},
                headers={"User-Agent": "TopoTile-Studio/0.1 (local desktop 3D-printing app)"},
                timeout=(10, 60),
            )
            if response.status_code >= 400:
                excerpt = " ".join(response.text.split())[:240]
                raise RuntimeError(f"HTTP {response.status_code} {excerpt}")
            payload = response.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"Open-Meteo elevation request failed: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError(f"Open-Meteo elevation returned invalid JSON: {exc}") from exc

        values = payload.get("elevation")
        if not isinstance(values, list) or len(values) != len(chunk):
            raise RuntimeError("Open-Meteo elevation returned an unexpected response shape.")
        for value in values:
            elevations.append(np.nan if value is None else float(value))
    return elevations


def make_auto_elevation_terrain(projection: LocalProjection, scaler: ModelScaler, params: ModelParams) -> TerrainGrid:
    max_cells = min(params.terrain_grid_size, AUTO_ELEVATION_MAX_GRID_SIZE)
    xx_m, yy_m, lonlat = _terrain_grid_points(projection, scaler, max_cells)
    values = fetch_open_meteo_elevations(lonlat)
    elev = np.array(values, dtype=float).reshape(xx_m.shape)
    terrain = _terrain_from_elevation(elev, xx_m, yy_m, scaler, params)
    if terrain is None:
        raise RuntimeError("Auto terrain download returned no usable elevation values.")
    return terrain


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2 ** zoom
    lat = max(-85.05112878, min(85.05112878, lat))
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def _terrain_tile_path(zoom: int, x: int, y: int) -> Path:
    return TERRAIN_TILE_CACHE / str(zoom) / str(x) / f"{y}.tif"


def _download_terrain_tile(zoom: int, x: int, y: int) -> Path:
    path = _terrain_tile_path(zoom, x, y)
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    url = TERRAIN_TILE_URL.format(z=zoom, x=x, y=y)
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "TopoTile-Studio/0.1 (local desktop 3D-printing app)"},
            timeout=(10, 90),
        )
        if response.status_code >= 400:
            excerpt = " ".join(response.text.split())[:240]
            raise RuntimeError(f"HTTP {response.status_code} {excerpt}")
    except requests.RequestException as exc:
        raise RuntimeError(f"Terrain tile download failed for {zoom}/{x}/{y}: {exc}") from exc
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(response.content)
    tmp.replace(path)
    return path


def fetch_terrain_tile_elevations(lonlat: list[tuple[float, float]], zoom: int) -> list[float]:
    try:
        import rasterio
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("rasterio is required for terrain tile support") from exc

    grouped: dict[tuple[int, int], list[tuple[int, float, float]]] = {}
    for index, (lon, lat) in enumerate(lonlat):
        tile = lonlat_to_tile(lon, lat, zoom)
        grouped.setdefault(tile, []).append((index, lon, lat))

    elevations = [np.nan] * len(lonlat)
    for (x, y), samples in grouped.items():
        path = _download_terrain_tile(zoom, x, y)
        with rasterio.open(path) as src:
            to_tile = Transformer.from_crs("EPSG:4326", src.crs or "EPSG:3857", always_xy=True)
            points = [to_tile.transform(lon, lat) for _, lon, lat in samples]
            for (index, _, _), value in zip(samples, src.sample(points)):
                elevation = float(value[0])
                if src.nodata is not None and abs(elevation - float(src.nodata)) < 1e-9:
                    elevation = np.nan
                elevations[index] = elevation
    return elevations


def make_terrain_tile_terrain(projection: LocalProjection, scaler: ModelScaler, params: ModelParams) -> TerrainGrid:
    xx_m, yy_m, lonlat = _terrain_grid_points(projection, scaler, params.terrain_grid_size)
    values = fetch_terrain_tile_elevations(lonlat, params.terrain_tile_zoom)
    elev = np.array(values, dtype=float).reshape(xx_m.shape)
    terrain = _terrain_from_elevation(elev, xx_m, yy_m, scaler, params)
    if terrain is None:
        raise RuntimeError("Terrain tiles returned no usable elevation values.")
    return terrain


def make_terrain(
    dem_path: str | Path | None,
    projection: LocalProjection,
    scaler: ModelScaler,
    params: ModelParams,
) -> tuple[TerrainGrid, str]:
    if dem_path:
        return make_dem_terrain(dem_path, projection, scaler, params), "uploaded_dem"
    if params.auto_terrain and params.large_map_mode:
        return make_terrain_tile_terrain(projection, scaler, params), "terrain_tiles"
    if params.auto_terrain:
        return make_auto_elevation_terrain(projection, scaler, params), "auto_elevation"
    return make_flat_terrain(projection, scaler, params), "flat"
