# Changelog

All notable changes to TopoTile Studio / 3D地图工坊 are recorded here.

Time zone: local macOS time. Some early entries are reconstructed from request order, screenshots, backup names, and file modification times.

## 2026-07-04

### 11:58 - Printable Flat Skillion Building Parts and Version 0.57

- Fixed high-detail palace/eave blocks whose side edges were repaired but whose tops still appeared sunken or sloped.
- Changed `building:part=yes` features tagged with `roof:shape=skillion` to print as flat cuboid-like blocks instead of sloped roof wedges.
- Kept explicit `gabled`, `hipped`, `pyramidal`, and `dome` roof handling in High detail mode.
- Verified the Tiananmen high-detail cached job: all 232 raw `skillion` building parts are now treated as flat printable parts, and the full building mesh remains watertight with zero non-manifold edges.
- Added a regression test for printable flat `skillion` building parts and updated the app version to `v0.57`.

### 11:23 - Direction-Aware High Detail Roof Parts and Version 0.56

- Fixed the remaining palace-style high-detail roof/eave parts that still appeared as triangular or missing-corner cuboids after the closed-mesh fix.
- Passed `roof:direction` and `roof:orientation` tags into the actual high-detail building export path.
- Generated `skillion` roof parts from their real four-point footprints first, then used OSM compass direction values such as `88.5`, `178.5`, `268.5`, and `358.5` to place the high and low sides correctly.
- Allowed only direction-tagged `skillion` roof parts to use a narrow near-rectangle fallback, so long eave pieces are stabilized without forcing normal complex buildings into rectangles.
- Added regression tests for direction-aware high-detail roofs and updated the app version to `v0.56`.

### 10:57 - Closed High Detail Roof Meshes and Version 0.55

- Replaced the previous roof-bottom removal approach with closed high-detail roof solids so exported roof/body geometry no longer leaves open contour edges.
- Added analytic closed meshes for rectangular `gabled`, `skillion`, `hipped`, and `pyramidal` OSM roofs, which fixes narrow palace-style roof and eave parts that previously appeared as broken triangular edges.
- Rebuilt `dome` roofs with a higher-resolution radial mesh so landmark domes such as the National Centre for the Performing Arts render smoother and remain watertight.
- Added a safety fallback that downgrades unsupported irregular roof footprints to flat closed building solids instead of exporting malformed high-detail roof geometry.
- Updated the app version to `v0.55`.

### 10:02 - Roof Coplanar Face Fix and Version 0.54

- Superseded by the 10:57 closed-roof fix after real Tiananmen high-detail geometry showed that roof-bottom removal still left open contour edges.
- Removed high-detail generated roof bottom faces from the normal building export path to avoid coplanar flicker/triangular artifacts against building bodies and stacked building parts.
- Increased dome/round roof sampling resolution for smoother hemispherical and spherical landmark roofs.
- Updated version numbering to the single-decimal project scheme and display it as `v0.54` in the app while keeping the internal version value as `0.54`.

## 2026-07-03

### 23:58 - High Detail Roof Mesh Closure Fix

- Fixed malformed high-detail roof/body geometry where internal roof triangulation edges could be treated as side walls.
- Changed OSM roof mesh side generation to use only the building footprint exterior boundary.
- Added watertight/non-manifold regression coverage for gabled, hipped, pyramidal, skillion, and dome roof meshes.
- Bumped the web app version to `v0.36.17`.

### 23:41 - Default Overture Building Supplement

- Added default Overture Maps building-footprint supplementation when the Buildings layer is enabled.
- Kept OSM buildings as the primary source and skipped Overture footprints that overlap existing OSM building geometry.
- Reused the existing Normal and High detail building generation paths, so supplemental footprints can use Overture height, floor, and roof tags when available.
- Cached Overture building batches under the OSM cache folder and kept generation soft-fail when the supplemental source is unavailable.
- Added Overture attribution to generated `ATTRIBUTION.txt`, `README.md`, and `NOTICE.md`.
- Bumped the web app version to `v0.36.16`.

### 22:56 - OSM Roof Shapes in High Detail Mode

- Added High detail building generation for explicit OSM `roof:shape` tags.
- Supported printable approximations for gabled, hipped, pyramidal, skillion, and dome/round roofs.
- Used `roof:height` / `roof:levels` when present while keeping total building height bounded by the OSM building height.
- Left Normal mode unchanged and skipped unsupported or missing roof-shape tags.
- Bumped the web app version to `v0.36.15`.

### 19:26 - Move Rail and Subway Line Controls

- Moved `Rail lines` and `Subway lines` from the main `Layers` section into the `Road Levels` checkbox group.
- Kept `Rail stations` and `Subway stations` in the main `Layers` section because they are station marker layers rather than line levels.
- Updated the English and Chinese helper text to reflect the new control placement.
- Bumped the web app version to `v0.36.14`.

### 19:20 - Optional Rail and Subway Layers

- Added four default-off layer switches: `Rail lines`, `Rail stations`, `Subway lines`, and `Subway stations`.
- Added OSM fetching and parsing for railway tracks, subway tracks, railway stations, subway stations, and subway entrances.
- Generated rail/subway lines as low terrain-following strips and station nodes as small printable station markers.
- Added rail/subway feature counts to generation summaries and print-color grouping support for 3MF export.
- Bumped the web app version to `v0.36.13`.

### 17:17 - 3MF Print Color Groups

- Replaced the previous random export coloring behavior with stable 3MF-only print color groups.
- Kept web preview and GLB colors unchanged while writing grouped 3MF print colors: green for green space, blue for water, gray for roads, and white for buildings, parking, airport, and area infill.
- Renamed the setting to `3MF print color groups` / `3MF 打印图层分色` and saved it as `export_print_color_groups`.
- Kept compatibility with older project files that still contain `random_export_colors`.
- Bumped the web app version to `v0.36.12`.

### 17:04 - Random Color Defaults and Monument Shape

- Changed `Random colors on export` to be enabled by default for new and older loaded project configurations.
- Refined high-detail monument generation into a lower stepped base plus a slimmer rectangular stele/obelisk body.
- Tightened monument geometry tests so landmark tops must be visibly narrower than their bases.
- Bumped the web app version to `v0.36.11`.

### 14:30 - Random Export Colors

- Added a `Random colors on export` option in the export settings.
- When enabled, 3MF and GLB exports get randomized non-terrain layer colors while STL geometry remains unchanged.
- Added random color metadata to `summary.json` for generated jobs.
- Saved and loaded `random_export_colors` in project JSON files.
- Bumped the web app version to `v0.36.10`.

### 14:15 - Model Detail Mode

- Added a `Model detail` control above the map selection section with `Normal` and `High detail` modes.
- Kept `Normal` mode as the existing simplified, print-friendly building workflow.
- Added first-pass `High detail` building logic that prefers OSM `building:part` geometry over parent building blocks, respects `min_height`/`min_level`, and gives monument-style landmarks a stepped low-poly shape when OSM tags identify them.
- Saved and loaded `model_detail_mode` in project JSON files.
- Bumped the web app version to `v0.36.9`.

## 2026-07-01

### 18:33 - Public Release v0.36.8

- Prepared `v0.36.8` as the public release for the selection radius input.
- Bumped the app version from `v0.36.7` to `v0.36.8`.

### 18:07 - Selection Radius Input

- Added a `Center-to-edge radius, km` control below the north/east coordinate inputs.
- The radius control resizes fixed-ratio, circle, and hex selections around the current center.
- Kept Free selection mode as manual drag-only so it does not conflict with arbitrary rectangle editing.

### 17:40 - Public Release v0.36.7

- Prepared `v0.36.7` as a Windows launcher archive fix.
- Added `.gitattributes` so generated release archives preserve Windows `.bat` launchers with CRLF line endings.
- Bumped the app version from `v0.36.6` to `v0.36.7`.

### 16:43 - Public Release v0.36.6

- Prepared `v0.36.6` as a public release after renaming the one-click launchers.
- Bumped the app version from `v0.36.5` to `v0.36.6`.

### 16:38 - Launcher File Names

- Renamed the macOS launcher to `A-Start-MacOS-TopoTile_Studio(macOS点这个启动).command`.
- Renamed the Windows launcher to `A-Start-Windows-TopoTile_Studio(Windows点这个启动).bat`.
- Renamed the offline test launcher to `A-Test_Offline(离线测试).command`.
- Updated README launcher references to match the new file names.

### 01:35 - Product Name and Intro

- Set the bilingual product name to `TopoTile Studio / 3D地图工坊`.
- Updated the main intro to `把真实地图生成可 3D 打印的城市与地形模型。`
- Updated the web header, README overview, local launchers, generated attribution, and app metadata to use the bilingual name.
- Bumped the app version to `v0.36.5`.

### 01:23 - Dedication Easter Egg

- Added a subtle one-line dedication at the bottom of the left toolbar.
- Bumped the app version to `v0.36.4`.

### 01:16 - Offline Test Button Placement

- Moved the `Offline Test Model` button and helper text above the `Mesh repair` controls in the left toolbar.

### 01:06 - Selection Edge Drag Handles

- Added draggable handles on the north, east, south, and west edges of the map selection box.
- Free selection mode now supports dragging a single side independently.
- Fixed-ratio, circle, and hex selection modes keep their locked proportions when resizing from an edge.
- Bumped the app version to `v0.36.3`.

### 00:53 - Preview Reset and Completion Timestamp

- Added a `Reset position` button in the 3D preview toolbar to return the preview pan offset to the original centered position.
- Added a backend `completed_at` timestamp for normal and offline sample jobs using local 24-hour `YYYY-MM-DD HH:mm` format.
- Shows the generated-at timestamp in the left completion log.
- Bumped the app version to `v0.36.2`.

### 00:40 - Preview Pan Rewrite

- Rewrote middle-mouse preview panning as a pure 2D screen-space shift of the preview layer instead of changing the 3D camera target.
- Intercepts middle-button pointer and mouse events at the preview container before `model-viewer` can treat them as orbit controls.
- Resets the 2D preview pan when a new model loads and keeps the exported 3MF geometry unchanged.
- Bumped the app version to `v0.36.1`.

### 00:18 - Middle-Mouse Preview Pan

- Added middle-mouse drag panning in the 3D preview so the model can be moved up, down, left, and right within the preview pane without changing exported geometry.
- Kept left-button orbit rotation and mouse-wheel zoom behavior intact.
- Temporarily pauses auto-rotate while panning, then restores it if the auto-rotate switch remains enabled.
- Bumped the app version to `v0.36.0`.

### 00:01 - Beginner-Friendly Python Runtime Launchers

- Updated the macOS launcher to detect Python 3.11/3.12 specifically instead of any Python 3 version.
- Added bilingual English/Chinese startup prompts with step markers such as `(1/3)`, `(2/3)`, and `(3/3)`.
- Added optional macOS automatic setup: install Homebrew after confirmation when needed, then install Python 3.12 and continue startup.
- Updated the Windows launcher to detect Python 3.11/3.12 and optionally install Python 3.12 through `winget` after confirmation.
- Existing unsupported `.venv` environments are recreated with a supported Python version.
- Updated README startup instructions for the new automatic setup flow.

## 2026-06-30

### 23:31 - GitHub Publishing Legal Docs

- Added `LICENSE` using CC BY-NC-SA 4.0 with explicit source-available, non-commercial, ShareAlike, and modified-source availability intent.
- Added `NOTICE.md` with OSM attribution, public API usage notes, and third-party-name notices.
- Added `DISCLAIMER.md` covering data accuracy, printability, and as-is use limitations.
- Added `SECURITY.md` explaining local-only use and avoiding public internet exposure.
- Updated the README with Beta status, bilingual license summary, public API limits, OSM attribution links, and legal document references.

### 21:49 - Large Area Infill and Water Recovery Fixes

- Changed `All area polygons` infill so very large parent polygons are automatically skipped when they cover dense existing detail such as roads, buildings, water, green areas, parking, airport pavement, or smaller infill polygons.
- Added automatic supplemental water-boundary fetching for large selections when the water layer is enabled, triggered by selection size instead of `large_map_mode`.
- Added OSM relation-member geometry recovery so water multipolygons can be rebuilt from separately returned member ways.
- Added separate caching and merge handling for supplemental water Overpass responses, keeping richer duplicate geometry without dropping other OSM layers.
- Bumped the app version to `v0.35.0`.

### 20:17 - Cancel Running Generation

- Added a `Stop current job` control that can cancel the active generation from the web UI.
- Added `POST /api/jobs/{job_id}/cancel` with queued-job cancellation and running-job cooperative cancellation.
- Threaded cancellation checks through OSM tiled downloads, Open-Meteo elevation batches, terrain tile downloads, model generation, mesh repair/export checkpoints, chunk export, and the bundled offline sample.
- Cancelled jobs now clean incomplete output files while keeping reusable OSM/elevation/terrain cache data.
- Added English/Chinese UI text for cancelling/cancelled states.
- Bumped the app version to `v0.34.0`.

### 17:46 - English/Chinese Interface Toggle

- Added a header language switch for English and Chinese UI text.
- Translated main form labels, buttons, helper text, selection hints, terrain/cache/project messages, generation status, download labels, and common printability warnings.
- Saved the preferred language in browser local storage so the page keeps the selected language after reload.
- Bumped the app version to `v0.33.0`.

### 17:24 - Offline Sample Button English Label

- Changed the built-in sample button label from `离线测试模型` to `Offline Test Model`.

### 17:18 - Header Author Text

- Changed the page header author credit from `Shuishi.Wen` to `Made by Wenshuishi`.

### 17:09 - Offline Sample Label and Author Credit

- Renamed the visible built-in sample button to `离线测试模型` so the sample content is not directly exposed in the UI.
- Changed visible sample helper text, backend status text, script output, and one-click script naming to generic offline-test-model wording.
- Changed offline sample export file names to generic `offline_test_model.*` names.
- Added the author credit `Shuishi.Wen` to the top-right of the page header.
- Bumped the app version to `v0.32.1`.

### 16:58 - Built-in Tiananmen Offline Sample

- Replaced the previous synthetic offline sample with a bundled Tiananmen test model based on the provided `天安门-测试.3mf` and project JSON.
- The offline sample now generates `.3mf`, `.glb`, `.stl`, attribution text, summary JSON, and project JSON without using OSM/API network access.
- Moved the sample button near the top of the left toolbar and renamed it `Tiananmen offline sample` so it is easier to find.
- Added `Open_Tiananmen_Offline_Sample.command` as a one-click macOS script that exports the bundled sample into `~/Downloads/TopoTile_Tiananmen_Offline_Sample/`.
- Updated sample generation docs and tests for the bundled Tiananmen sample.
- Bumped the app version to `v0.32.0`.

### 16:35 - GPX/KML Raised Route Layer

- Added a `Route / Track` layer that accepts GPX or KML files and prints the track as an independent raised line over the model.
- Added route controls for width, height, and terrain offset, plus map preview, clear route, and fit-selection-to-route actions.
- Saved route points in project JSON so loaded projects can regenerate the same route without requiring the original GPX/KML file.
- Routed uploaded GPX/KML files through backend parsing during job submission so generation uses validated route data.
- Generated route meshes as their own red `route` mesh part that follows terrain relief and stays raised over cut-out water crossings.
- Bumped the app version to `v0.31.0`.
- Added regression coverage for GPX/KML parsing, saved route parameters, terrain-following route meshes, and full model generation with a route part.

### 15:43 - Project Handoff Notes

- Added `HANDOFF.md` with current version, run commands, backup state, architecture notes, geometry design decisions, validation projects, risk areas, and backup workflow.

### 14:45 - Terrain-Fitted Building Bases

- Changed terrain-mode building extrusion so building bottoms follow sampled terrain instead of using one flat centroid height.
- Kept building roofs flat by using one roof plane per building.
- Used a median-terrain roof baseline with a minimum high-side wall height so steep slopes avoid floating without excessively inflating normal building height.
- Bumped the app version to `v0.30.0`.
- Added regression coverage for slope buildings with terrain-following bases, flat roofs, and clean mesh diagnostics.

### 14:14 - App Version Label

- Set the current application version to `v0.29.0`.
- Added the version number as a small label next to the TopoTile Studio title in the web app.
- Added `app_version` to saved project JSON files while keeping the existing project schema version unchanged.

### 13:17 - Adjustable Map Preview Layout and Keyboard Selection Nudging

- Added a draggable horizontal divider between the map and 3D preview panes so their vertical ratio can be adjusted with the mouse.
- The adjusted map/preview split is saved in local browser storage and restored on reload.
- Added keyboard nudging for the map selection: hover the blue center handle, then use arrow keys to move the whole selection by small screen-pixel steps.
- Direction-key nudging ignores form inputs so numeric fields and text boxes keep their normal keyboard behavior.

### 12:21 - Windows One-Click Launcher

- Added `Open_TopoTile_Studio_Windows_Start.bat` as a Windows-specific double-click launcher.
- The Windows launcher creates `.venv`, installs missing dependencies, starts TopoTile Studio on `127.0.0.1:8000`, and opens the browser automatically.
- Updated the README run instructions to list both the macOS launcher and the Windows launcher.

### 09:53 - Non-Manifold Repair Hardening

- Created a local pre-change backup at `/Users/apple/Documents/Codex/2026-06-30/topotile_studio_backup_20260630-093242`.
- Changed polygon extrusion to reuse vertices inside each individual solid so buildings, water, green, parking, airport, and area infill blocks are generated closed before repair.
- Changed automatic repair to evaluate multiple candidates and avoid accepting vertex merges that create more non-manifold or overused edges.
- Added optional fan hole filling as a repair candidate for terrain-following surfaces.
- Changed terrain-following surface extrusion to build side walls from the actual triangulated top-surface boundary, preventing side walls from drifting away from terrain triangle boundaries.
- Filtered unprintable tiny or point-touching holes that can create overused vertical edges in water and green layers.
- Verified prior problematic cached projects offline: `奥体1`, `南通天虹花园`, and terrain-mode `西山红色之旅3` now report `0` remaining non-manifold edges after generation.
- Added regression coverage for closed extrusion, adjacent solids, and unprintable touching holes.

### 09:21 - Area Infill and Cache Cleanup Defaults

- Changed the default `Area infill height, mm` from `0.40 mm` to `0.60 mm`.
- Set `Include OSM cache`, `Include elevation cache`, and `Include terrain cache` to checked by default in the Maintenance section.
- Updated parameter regression coverage for the new area infill height default.

### 08:50 - OSM and Elevation Data Cache

- Added shared OSM Overpass response caching under `data/cache/osm/`.
- Added Open-Meteo elevation response caching under `data/cache/elevation/open_meteo/`.
- Existing large-map terrain tile caching remains under `data/cache/terrain_tiles/`.
- Reusing the same map area and terrain sampling points now avoids repeated API downloads when the cache has not been cleared.
- Expanded cache status and cleanup controls to show and optionally clear OSM, elevation, and terrain tile caches separately.
- Added regression tests for OSM cache hits, Open-Meteo cache hits, and cache cleanup behavior.

### 07:51 - Area Infill Modes

- Replaced the previous footprint-cutout infill behavior with explicit area-level modes.
- Added `Area infill mode` in the UI and project JSON.
- `No-building areas` is now the default: if a broad area contains any mapped building, the whole area is skipped.
- `All area polygons` generates the full broad-area polygon even when buildings exist inside it.
- Verified the Nantong Tianhong Garden data: 477 of 570 candidate area polygons are skipped in default mode because they already contain buildings.
- Added regression tests for both area-level skip mode and full polygon mode.

### 00:05 - Area Infill Building Priority Fix

- Fixed area infill overlapping building footprints after projection and simplification.
- Changed area infill cleanup to subtract explicit features in final model millimeter coordinates before extrusion.
- Added a small building safety clearance so broad-area fill leaves mapped buildings completely reserved.
- Verified the Nantong Tianhong Garden project data: area infill/building overlap is now `0.0 mm²`.
- Added a regression assertion that area infill top faces do not intersect building footprints.

## 2026-06-29

### 23:28 - Broad Area Infill Layer

- Added an `Area infill` layer enabled by default for broad OSM area tags that often represent districts or facility zones rather than individual buildings.
- Added `Area infill height, mm`, defaulting to `0.40 mm`, so the low fill layer can be adjusted independently from parking lots.
- Extended OSM fetching and parsing for broad area tags including residential/industrial/commercial landuse, hospitals, schools, healthcare sites, theme parks, historic districts, city blocks, works, and office areas.
- Area infill now subtracts existing buildings, roads, water, green areas, parking, and airport pavement before generating, so real mapped objects remain intact and only leftover empty area is filled.
- Added regression coverage for defaults, saved parameter parsing, Overpass query coverage, broad-area classification, and mesh cutouts around explicit features.

### 22:54 - Closed River Ring Water/Land Fix

- Fixed closed `waterway=river|canal|stream|ditch|drain` ways being treated as filled water polygons.
- Closed linear waterways are now buffered as waterways instead of filling the enclosed land area.
- Kept true water-area tags such as `natural=water`, `water=*`, `waterway=riverbank`, and `area=yes` as filled water polygons.
- Verified the Nantong Tianhong Garden project using saved OSM data: the closed Hao River way is now parsed as a line, preventing the surrounded urban land from being covered by water.
- Added regression coverage so closed river rings do not erase land/building/green layers in similar four-sided-water areas.

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
