# Roadmap for the next iteration

## High-priority improvements

1. Add automatic DEM download.
   - Global: Copernicus DEM GLO-30 or another open DEM source with clear attribution.
   - US: USGS 3DEP.
   - Keep manual GeoTIFF upload as the reliable fallback.

2. Improve OSM multipolygon support.
   - Reconstruct relation outers and inners.
   - Preserve holes in parks, lakes, and large building complexes.

3. Add real 3MF color/material metadata.
   - Current version exports separate 3MF objects.
   - Bambu Studio can assign colors/materials manually.
   - Next version should write standard 3MF material groups safely.

4. Add slicer-oriented model checks.
   - Warn when the model exceeds Bambu A1 bed-safe limits.
   - Warn when a layer is thinner than printable defaults.
   - Add triangle/vertex budget warnings.

5. Add terrain-following roads and water.
   - Current surface layers use the representative point height.
   - Better version should drape features onto the terrain grid.

6. Add tile splitting.
   - Split large areas into 2x2 or 3x3 print tiles.
   - Add labels and optional connector geometry.

## Good Codex task prompt

Implement automatic USGS 3DEP DEM fetching for selected bbox in the existing FastAPI app. Preserve the manual DEM upload path. Add a DEM provider abstraction so later Copernicus DEM can be added. Return clear error messages when DEM download fails, and update README with attribution and usage instructions.
