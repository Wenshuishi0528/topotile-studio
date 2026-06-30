import numpy as np

from city_modeler.dem import fetch_open_meteo_elevations, lonlat_to_tile, make_auto_elevation_terrain
from city_modeler.geo import make_local_projection, make_scaler
from city_modeler.params import ModelParams


class FakeResponse:
    def __init__(self, elevations):
        self.status_code = 200
        self.text = ""
        self._elevations = elevations

    def json(self):
        return {"elevation": self._elevations}


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
