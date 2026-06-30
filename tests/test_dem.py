import numpy as np
import pytest

from city_modeler import dem
from city_modeler.dem import TerrainGrid, fetch_open_meteo_elevations, lonlat_to_tile, make_auto_elevation_terrain, make_terrain
from city_modeler.geo import make_local_projection, make_scaler
from city_modeler.params import ModelParams


class FakeResponse:
    def __init__(self, elevations):
        self.status_code = 200
        self.text = ""
        self._elevations = elevations

    def json(self):
        return {"elevation": self._elevations}


@pytest.fixture(autouse=True)
def isolate_open_meteo_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(dem, "OPEN_METEO_CACHE", tmp_path / "open_meteo")


def test_fetch_open_meteo_elevations_batches_100_points(monkeypatch):
    calls = []

    def fake_get(url, params, headers, timeout):
        count = len(params["latitude"].split(","))
        calls.append(count)
        return FakeResponse([float(len(calls))] * count)

    monkeypatch.setattr("requests.get", fake_get)

    lonlat = [(-122.0, 47.0 + i * 0.0001) for i in range(101)]
    elevations = fetch_open_meteo_elevations(lonlat)

    assert calls == [100, 1]
    assert len(elevations) == 101
    assert elevations[0] == 1.0
    assert elevations[-1] == 2.0


def test_fetch_open_meteo_elevations_reuses_cache(monkeypatch):
    calls = []

    def fake_get(url, params, headers, timeout):
        count = len(params["latitude"].split(","))
        calls.append(count)
        return FakeResponse([42.0] * count)

    monkeypatch.setattr("requests.get", fake_get)

    lonlat = [(-122.0, 47.0), (-121.999, 47.001)]
    first = fetch_open_meteo_elevations(lonlat)
    second = fetch_open_meteo_elevations(lonlat)

    assert first == [42.0, 42.0]
    assert second == first
    assert calls == [2]


def test_lonlat_to_tile_is_stable_for_known_coordinate():
    assert lonlat_to_tile(-122.3321, 47.6062, 13) == (1312, 2860)


def test_make_auto_elevation_terrain_has_relief(monkeypatch):
    def fake_get(url, params, headers, timeout):
        lats = [float(v) for v in params["latitude"].split(",")]
        lons = [float(v) for v in params["longitude"].split(",")]
        elevations = [(lat - min(lats)) * 1000 + (lon - min(lons)) * 1000 for lat, lon in zip(lats, lons)]
        return FakeResponse(elevations)

    monkeypatch.setattr("requests.get", fake_get)
    params = ModelParams(
        south=47.0,
        west=-122.0,
        north=47.01,
        east=-121.99,
        auto_terrain=True,
        terrain_grid_size=6,
        vertical_exaggeration=2,
    )
    projection = make_local_projection(*params.bbox_tuple)
    scaler = make_scaler(projection.width_m, projection.height_m, params.max_size_mm)

    terrain = make_auto_elevation_terrain(projection, scaler, params)

    assert terrain.nx == 6 or terrain.ny == 6
    assert np.max(terrain.z_mm) > np.min(terrain.z_mm)
    assert np.min(terrain.z_mm) == params.base_thickness_mm


def test_large_map_without_auto_terrain_stays_flat(monkeypatch):
    def fail_terrain_tiles(*args, **kwargs):
        raise AssertionError("terrain tiles should not be used for flat large-map mode")

    monkeypatch.setattr("city_modeler.dem.make_terrain_tile_terrain", fail_terrain_tiles)
    params = ModelParams(
        south=47.0,
        west=-122.0,
        north=47.01,
        east=-121.99,
        large_map_mode=True,
        auto_terrain=False,
        vertical_exaggeration=10,
    )
    projection = make_local_projection(*params.bbox_tuple)
    scaler = make_scaler(projection.width_m, projection.height_m, params.max_size_mm)

    terrain, source = make_terrain(None, projection, scaler, params)

    assert source == "flat"
    assert terrain.nx == 2
    assert terrain.ny == 2
    assert np.allclose(terrain.z_mm, params.base_thickness_mm)


def test_large_map_with_auto_terrain_uses_terrain_tiles(monkeypatch):
    def fake_terrain_tiles(_projection, _scaler, params):
        return TerrainGrid(
            x_mm=np.asarray([[0.0, 10.0], [0.0, 10.0]]),
            y_mm=np.asarray([[0.0, 0.0], [10.0, 10.0]]),
            z_mm=np.asarray([[params.base_thickness_mm, params.base_thickness_mm + 2.0], [params.base_thickness_mm + 1.0, params.base_thickness_mm + 3.0]]),
        )

    monkeypatch.setattr("city_modeler.dem.make_terrain_tile_terrain", fake_terrain_tiles)
    params = ModelParams(
        south=47.0,
        west=-122.0,
        north=47.01,
        east=-121.99,
        large_map_mode=True,
        auto_terrain=True,
    )
    projection = make_local_projection(*params.bbox_tuple)
    scaler = make_scaler(projection.width_m, projection.height_m, params.max_size_mm)

    terrain, source = make_terrain(None, projection, scaler, params)

    assert source == "terrain_tiles"
    assert float(np.ptp(terrain.z_mm)) == 3.0
