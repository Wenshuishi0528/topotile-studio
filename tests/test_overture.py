from shapely.geometry import Polygon
from shapely import wkb

from city_modeler.geo import make_local_projection
from city_modeler.osm import OSMFeature
from city_modeler import overture


def _row(row_id: str, coords: list[tuple[float, float]]) -> dict[str, object]:
    return {
        "id": row_id,
        "geometry_wkb_hex": wkb.dumps(Polygon(coords), hex=True),
        "height": 12.0,
        "num_floors": 4,
        "roof_shape": "gabled",
        "roof_height": 2.0,
    }


def _local_polygon(coords: list[tuple[float, float]], projection) -> Polygon:
    return Polygon([projection.lonlat_to_local(lon, lat) for lon, lat in coords])


def test_overture_buildings_fill_gaps_without_overlapping_osm_buildings(tmp_path, monkeypatch):
    monkeypatch.setattr(overture, "OVERTURE_BUILDING_CACHE_DIR", tmp_path)
    projection = make_local_projection(39.90, 116.39, 39.91, 116.40)
    clip_m = projection.bbox_polygon_m
    overlap_coords = [
        (116.3910, 39.9010),
        (116.3920, 39.9010),
        (116.3920, 39.9020),
        (116.3910, 39.9020),
        (116.3910, 39.9010),
    ]
    gap_coords = [
        (116.3960, 39.9060),
        (116.3970, 39.9060),
        (116.3970, 39.9070),
        (116.3960, 39.9070),
        (116.3960, 39.9060),
    ]
    existing = [
        OSMFeature(
            layer="building",
            geometry_m=_local_polygon(overlap_coords, projection),
            tags={"building": "yes"},
            osm_id="way/1",
        )
    ]

    def fake_download(*args, **kwargs):
        return [_row("overlap", overlap_coords), _row("gap", gap_coords)], "test-release", False

    monkeypatch.setattr(overture, "_download_overture_rows", fake_download)

    features, result = overture.supplement_overture_buildings(
        39.90,
        116.39,
        39.91,
        116.40,
        projection,
        existing,
        clip_m,
    )

    assert result.status == "complete"
    assert result.source_rows == 2
    assert result.added == 1
    assert result.skipped_overlap == 1
    assert features[0].tags["source"] == "Overture Maps Foundation"
    assert features[0].tags["height"] == "12.00"
    assert features[0].tags["building:levels"] == "4"
    assert features[0].tags["roof:shape"] == "gabled"


def test_overture_buildings_reuse_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(overture, "OVERTURE_BUILDING_CACHE_DIR", tmp_path)
    projection = make_local_projection(39.90, 116.39, 39.91, 116.40)
    coords = [
        (116.3960, 39.9060),
        (116.3970, 39.9060),
        (116.3970, 39.9070),
        (116.3960, 39.9070),
        (116.3960, 39.9060),
    ]
    calls = {"count": 0}

    def fake_download(*args, **kwargs):
        calls["count"] += 1
        return [_row("cached", coords)], "test-release", False

    monkeypatch.setattr(overture, "_download_overture_rows", fake_download)
    first_features, first_result = overture.supplement_overture_buildings(
        39.90, 116.39, 39.91, 116.40, projection, [], projection.bbox_polygon_m
    )
    second_features, second_result = overture.supplement_overture_buildings(
        39.90, 116.39, 39.91, 116.40, projection, [], projection.bbox_polygon_m
    )

    assert calls["count"] == 1
    assert len(first_features) == 1
    assert len(second_features) == 1
    assert first_result.cache_hit is False
    assert second_result.cache_hit is True
