# Changelog

All notable changes to TopoTile Studio are recorded here.

Time zone: local macOS time on 2026-06-29. Some early entries are reconstructed from request order, screenshots, backup names, and file modification times.

## 2026-06-29

### 22:36 - Automatic Mesh Repair for Non-Manifold Edges

- Added automatic mesh repair before exporting `.3mf`, `.glb`, and `.stl` files.
- Removed common degenerate faces, duplicate faces, duplicate vertices, inconsistent winding, inverted normals, and simple holes during generation.
- Added a default-on `Auto repair non-manifold edges` option in the web UI.
- Added mesh repair diagnostics to job summaries and the on-page generation status.
- Added printability warnings when non-manifold edges remain after automatic repair.
- Added regression tests for mesh repair, parameter save/load, and full generation summaries.

### 22:28 - Flat vs Terrain Mode Separation

- Rechecked flat and terrain generation as separate modes.
- Changed Large Map Mode so it only controls tiled OSM fetching; terrain relief now requires `Auto terrain relief` or an uploaded DEM.
- Preserved the existing large terrain workflow when both Large Map Mode and Auto Terrain Relief are enabled.
- Added a terrain-mode status hint in the web UI and exposed `Max terrain height, mm` as a terrain-specific control.
- Disabled terrain-only controls in the UI when the current setup is flat-only.
- Added regression tests covering flat large-map mode and terrain-tile mode.

### 22:20 - Terrain-Draped Surface Layers and Complete Large-Map OSM Fetch

- Fixed terrain mode surface layers so green areas, water, parking, airport pavement, and roundabout surfaces follow sampled terrain instead of extruding as one flat slab.
- Added terrain-grid point sampling and boundary densification for large surface polygons so hillside parks and forests conform to terrain relief.
- Densified normal road segments in terrain mode so long roads follow slopes instead of spanning across terrain peaks as straight beams.
- Improved large-map OSM fetching to keep the richest duplicate geometry when a feature appears in multiple tiles.
- Added automatic subdivision retries for failed OSM tiles and stopped generation if any tile still fails, preventing partial exports with missing buildings, roads, or green areas.

### 21:18 - Airport Pavement Layer and Water/Green Surface Repair

- Added an `Airport` layer option enabled by default.
- Airport runways, taxiways, and aprons are parsed from `aeroway=runway|taxiway|apron`.
- Airport pavement is generated as a low layer with the same thickness as surface parking.
- Improved complex water and green-area surface triangulation with constrained triangulation.
- Reduced independent simplification on water, green, parking, and airport surfaces to avoid visible cracks between adjacent lake/park boundaries.
- Verified the Summer Palace / Xishan project from a saved project JSON and existing OSM raw data without making a new Overpass request.

### 20:45 - Custom Export File Names

- Added a `File name` field in the project panel.
- Applied the chosen safe filename to `.3mf`, `.glb`, `.stl`, chunk ZIP, chunk manifest, and numbered chunk `.3mf` files.
- Included filename settings in project save/load.
- Added tests for custom filenames and chunk filenames.

### 20:26 - Print Workflow Tools

- Added printability scoring before printing, including bed-size, base-thickness, road-width, terrain-relief, and mesh-density checks.
- Added chunk export with row/column settings and numbered files such as `r01_c01`.
- Added a downloadable chunk ZIP and chunk manifest.
- Added a road cleanup strength slider with detailed, balanced, clean, and major-road presets.
- Added project save/load as JSON.
- Added cache status and cache cleanup controls.
- Protected cache cleanup from deleting generated files while a current job is running.

### 18:47 - Address Search and Road Defaults

- Added address/place search using Nominatim so the current selection can move to a searched location.
- Moved the search control to the top of the left toolbar.
- Set `Footway width` and `Pedestrian width` defaults to `0.60 mm`.
- Enabled `Footway` and `Pedestrian` road levels by default.

### 15:26 - Selection Ratios and Terrain-Following Roads

- Added fixed selection ratios and shapes: free, `1:1`, `5:7`, `7:5`, circle, and regular hexagon.
- Kept fixed-ratio selections resizable through map dragging.
- Fixed road/bridge layers that floated above normal terrain.
- Roads now sample terrain height along their geometry so they follow sloped terrain more closely.
- Kept bridge clearance behavior only for water-cutout spanning cases.

### 15:13 - Backup Snapshot

- Created a backup of the working version under the Codex backup folder.

### 14:18 - More Green Feature Coverage and Path Width Controls

- Added support for more small green-area OSM tags, including closed `barrier=hedge`, `barrier=planter`, `man_made=planter`, `natural=shrubbery`, and flowerbed/plant-nursery landuse.
- Added independent width controls for `Footway` and `Pedestrian` road types.

### 14:00 - Water Cutout Bridge Fix

- Fixed roads and bridges crossing water cutouts so they do not incorrectly drop to the bottom plate.
- Preserved elevated bridge behavior where it is needed to span cut-out water.

### 13:43 - Water Cutout Mode

- Added `Cut out water` mode.
- Water polygons can now become through-holes in the base so colored paper, acrylic, or other material can be placed underneath.
- Added summary reporting for water-cutout polygon counts.

### 13:30 - Large Map Generation

- Added Large Map Mode for larger areas such as 10 km x 10 km workflows.
- Implemented tiled Overpass OSM fetching to reduce single-request failures.
- Added cached terrain GeoTIFF tile support for large terrain models.
- Kept one-click generation behavior from the web UI.

### 13:00 - Automatic Terrain Option

- Added an automatic terrain relief option.
- Integrated public elevation data for non-flat terrain bases.
- Kept manual DEM GeoTIFF upload as an override.

### 12:38 - Roundabout and Project Naming Pass

- Renamed the app to TopoTile Studio.
- Added outdoor surface parking lots as an optional low printable layer.
- Fixed roundabout generation so circular roads no longer collapse into radial spokes.
- Created a backup snapshot after the roundabout fix.

### 11:59 - Missing Buildings and Green Areas

- Improved OSM feature parsing so more buildings and green areas present in OSM appear in the generated model.
- Improved clipping and layer generation for dense campus/city selections.

### 11:41 - Bambu Studio Import Compatibility

- Fixed generated `.3mf` files that opened in the browser preview but failed in Bambu Studio.
- Verified the 3MF package contains valid geometry and slicer-readable model data.

### 11:13 - Road Controls, Water Recognition, and Download Flow

- Added multi-select road-level controls.
- Added direct `.3mf` download after generation.
- Cleaned road rendering so irregular road artifacts were reduced.
- Improved recognition for oceans, lakes, and other water features.

### 10:50 - Web App Access and Startup

- Fixed local web access at `http://127.0.0.1:8000/`.
- Added a macOS double-click launcher command for easy startup.
- Improved local dependency/startup behavior.

### 10:30 - Initial Project Review

- Reviewed the new OSM + DEM 3MF modeler project structure.
- Identified the core FastAPI backend, Leaflet frontend, OSM parsing, terrain generation, and 3MF/GLB/STL export flow.
