# TopoTile Studio Handoff

Last updated: 2026-06-30-2149

## Current State

- Project name: TopoTile Studio
- Current app version: `v0.36.7`
- Local project path: `/Users/apple/Downloads/osm_dem_3mf_modeler`
- GitHub remote: `https://github.com/Wenshuishi0528/topotile-studio.git`
- Current branch: `main`
- Latest pushed commit at handoff: pending `v0.36.7` Windows launcher archive fix
- Latest GitHub backup tag: `backup-20260630-184250`
- Latest local backup: `/Users/apple/Documents/Codex/2026-06-30/topotile_studio_backup_20260630-184250`
- Local web URL: `http://127.0.0.1:8000/`

At this handoff, the working tree includes an English/Chinese language switch, cancellable generation flow, automatic large-water-boundary recovery, and broad-parent area-infill suppression for large all-area exports. Running generation jobs can be asked to stop through `POST /api/jobs/{job_id}/cancel`; cancellation is cooperative, so an in-flight HTTP request may need to return or timeout before the job reaches `cancelled`.

## How To Run

macOS one-click launcher:

```text
Open_OSM_DEM_3MF_Modeler.command
```

Windows one-click launcher:

```text
Open_TopoTile_Studio_Windows_Start.bat
```

Offline test model one-click launcher:

```text
Open_Offline_Test_Model.command
```

Manual run:

```bash
cd /Users/apple/Downloads/osm_dem_3mf_modeler
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Test:

```bash
cd /Users/apple/Downloads/osm_dem_3mf_modeler
./.venv/bin/python -m pytest -q
```

Expected test count at handoff: `79 passed`.

## What The App Does

TopoTile Studio is a local FastAPI web app for generating 3D-printable city and terrain models from OpenStreetMap data and optional elevation data. The UI uses Leaflet for map selection and `model-viewer` for GLB preview. Exports include `.3mf`, `.glb`, `.stl`, attribution text, and optional numbered chunk ZIPs.

Main user-facing capabilities:

- Interactive map selection with free, `1:1`, `5:7`, `7:5`, circle, and hexagon modes.
- Draggable selection handles plus keyboard nudging from the blue center handle.
- Address search that moves the selection center.
- Adjustable vertical split between the map and 3D preview panes.
- Building, road, water, green, parking, airport, and area-infill layers.
- Road level multi-select, road cleanup strength, and independent Footway/Pedestrian widths.
- Flat base mode and terrain relief mode.
- Large-map mode with tiled OSM fetch and cached terrain tiles.
- Water cutout mode for hollow water areas.
- GPX/KML route upload for printing a raised track line over the model.
- Built-in offline test model from bundled 3MF/project JSON assets.
- Project save/load JSON.
- Printability scoring, mesh repair, cache cleanup, custom file names, and chunk export.
- macOS and Windows one-click launchers.

## Key Files

- `app/main.py`: FastAPI routes, job handling, file downloads, cache endpoints, geocoding endpoint.
- `app/static/index.html`: entire frontend UI, Leaflet map, preview controls, project save/load, form serialization.
- `city_modeler/params.py`: validated model parameters and defaults.
- `city_modeler/osm.py`: Overpass queries, OSM tiled fetching, caching, and OSM feature classification.
- `city_modeler/dem.py`: terrain generation, auto elevation, terrain tile cache, DEM handling.
- `city_modeler/mesh_ops.py`: core geometry generation for terrain, buildings, roads, water, green, parking, airport, and area infill.
- `city_modeler/mesh_repair.py`: non-manifold diagnostics and automatic repair candidate selection.
- `city_modeler/pipeline.py`: full model generation pipeline and export orchestration.
- `city_modeler/routes.py`: GPX/KML parsing and route projection/clipping helpers.
- `data/samples/offline_test_model.3mf`, `data/samples/offline_test_model_project.json`: bundled offline test model assets.
- `Open_Offline_Test_Model.command`: one-click macOS exporter for the bundled offline test model.
- `city_modeler/export_3mf.py`, `export_glb.py`, `export_stl.py`: model writers.
- `city_modeler/printability.py`: printability scoring.
- `CHANGELOG.md`: chronological history of user-visible changes.
- `README.md`: user-facing overview and run instructions.

## Important Design Decisions

### Flat Mode vs Terrain Mode

Treat flat mode and terrain mode as distinct workflows. Do not assume parameters or mesh behavior should be identical.

- Flat mode: base terrain is flat, buildings are standard vertical extrusions.
- Terrain mode: surface layers and roads sample terrain height. Buildings now use a dedicated terrain-aware extrusion.

### Terrain-Fitted Buildings

Current behavior in `city_modeler/mesh_ops.py`:

- Building bottom vertices sample terrain height over the building footprint.
- Building roofs stay flat using one roof plane per building.
- Roof height uses a median-terrain baseline plus building height.
- On steep slopes, roof height is raised enough to keep a minimum high-side wall height.

This was added to fix hillside buildings floating above terrain while preserving flat roofs.

### Surface Layers

Green, water, parking, airport, and area infill use terrain-following thin layers in terrain mode. Their side walls are built from the actual triangulated top-surface boundary; this avoids boundary mismatches and helped eliminate non-manifold edges.

### Route / Track Layer

GPX/KML route data is saved in project JSON as normalized `[lat, lon]` points. Uploaded route files are parsed again on the backend during job submission, then converted into local projected lines and clipped to the current footprint. Route meshes are independent red `route` parts; they do not depend on OSM road-level selection. In terrain mode the route samples terrain like roads. In water-cutout mode, route segments crossing water are lifted by bridge clearance.

### Built-In Offline Sample

The `/api/sample` endpoint and `Offline Test Model` UI button use bundled offline assets instead of synthetic OSM data. This path does not call OSM, Open-Meteo, or terrain tile APIs. It loads `data/samples/offline_test_model.3mf`, exports matching 3MF/GLB/STL/project JSON into the job output directory, and also supports the standalone `Open_Offline_Test_Model.command` script for direct export to `~/Downloads/TopoTile_Offline_Test_Model/`.

### Water Cutout

`Cut out water` removes water from the terrain/base so the printed model can be placed over colored material. Roads crossing cutout water are elevated by bridge clearance unless marked as tunnels. Be careful not to regress this when changing water or road code.

### Water And Green Cleanup

Tiny holes and point-touching holes are filtered before extrusion. This is intentional: OSM/geometry union operations often create microscopic holes or touch points that make Bambu Studio report non-manifold/overused edges.

### Area Infill

Area infill fills broad OSM area polygons that often represent districts or facilities but are not individual buildings.

Modes:

- `empty_areas`: default. If a broad area contains any mapped building, skip the whole area.
- `all_areas`: generate the broad polygon even if buildings exist inside.

The user specifically wanted these two modes separated.

### Non-Manifold Repair

The repair system no longer blindly merges vertices. It evaluates repair candidates and chooses the one with fewer non-manifold/overused/boundary edges. This prevents road intersections or adjacent solids from being welded into overused edges.

Do not reintroduce unconditional global `merge_vertices` without checking `tests/test_mesh_repair.py` and real cached project summaries.

### Caching

Caches are intentional and reduce API usage:

- OSM Overpass responses: `data/cache/osm/`
- Open-Meteo elevation responses: `data/cache/elevation/open_meteo/`
- Terrain tiles: `data/cache/terrain_tiles/`

Maintenance UI can clear generated outputs and optionally clear each cache category.

## Known Validation Projects

These cached/output projects were repeatedly used to verify fixes:

- `3dcd64717fe3` / `奥体1`: flat mode, previously had thousands of non-manifold edges.
- `f8771e389d98` / `南通天虹花园`: flat mode, four-sided-water area regression target.
- `043ed44642fe` / `西山红色之旅3`: terrain mode, hillside/terrain and mesh-repair stress case.

Useful offline terrain validation command:

```bash
cd /Users/apple/Downloads/osm_dem_3mf_modeler
rm -rf data/outputs/terrain_building_check_043ed44642fe
./.venv/bin/python - <<'PY'
import json
from pathlib import Path
from city_modeler.params import ModelParams
from city_modeler.pipeline import generate_model

job = "043ed44642fe"
params = ModelParams.from_dict(json.loads((Path("data/jobs") / job / "params.json").read_text(encoding="utf-8")))
summary = generate_model(
    params,
    Path("data/outputs") / f"terrain_building_check_{job}",
    osm_json_path=Path("data/outputs") / job / "osm_raw.json",
)
print(summary["mesh_repair"]["status"])
print(summary["mesh_repair"]["totals"]["after"])
PY
```

Expected recent result: `clean`, with `non_manifold_edges: 0`.

## High-Risk Areas

Be cautious when editing:

- `mesh_ops.py`: most geometry regressions happen here.
- `mesh_repair.py`: changing repair order can reintroduce Bambu Studio non-manifold warnings.
- `osm.py`: incomplete OSM fetches caused missing buildings/green/water in earlier versions.
- `pipeline.py`: controls flat vs terrain mode behavior and export order.
- `app/static/index.html`: currently a single large frontend file; changes can easily break UI serialization.

Regression risks the user has already encountered:

- Bambu Studio says `.3mf` contains no geometry or non-manifold edges.
- Roundabouts become radial spokes instead of rings.
- Water/green polygons disappear or fragment.
- Four-sided-water urban areas get swallowed by water.
- Terrain mode surface layers float instead of following terrain.
- Roads/bridges float when not in water-cutout bridge mode.
- Area infill overlaps or replaces actual mapped buildings.
- Large OSM selections hit public API rate limits or partial tile failures.

## Versioning Guidance

Current version is `v0.36.7`.

The user counted 29 recorded iterations before adding terrain-fitted building bases. Terrain-fitted building bases became `v0.30.0`; GPX/KML raised routes became `v0.31.0`; the built-in offline sample became `v0.32.0`; generic sample labeling and author credit became `v0.32.1`; the English/Chinese UI toggle became `v0.33.0`; cancellable generation jobs became `v0.34.0`; broad-parent area-infill suppression and automatic large-water-boundary recovery became `v0.35.0`; one-click launcher renaming became `v0.36.6`; the Windows launcher release archive line-ending fix became `v0.36.7`.

Suggested rule:

- User-visible feature or behavior change: bump minor-like iteration, e.g. `v0.33.0`.
- Small bug fix or docs-only change: use patch, e.g. `v0.32.1`, unless the user wants every change counted as an iteration.

Places to update version:

- `app/static/index.html`: `APP_VERSION` and fallback header label.
- `city_modeler/__init__.py`: `__version__`.
- `CHANGELOG.md`: add a timestamped entry.

## Git And Backup Workflow

The user often asks for both local and GitHub backups.

Typical local backup:

```bash
backup_dir="/Users/apple/Documents/Codex/2026-06-30/topotile_studio_backup_YYYYMMDD-HHMMSS"
mkdir -p "$backup_dir"
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  /Users/apple/Downloads/osm_dem_3mf_modeler/ "$backup_dir"/
```

Typical GitHub backup:

```bash
git add <changed files>
git commit -m "<clear message>"
git tag backup-YYYYMMDD-HHMMSS
git push origin main
git push origin backup-YYYYMMDD-HHMMSS
```

Use the `::git-stage`, `::git-commit`, and `::git-push` final-response directives only after those actions actually succeed.

## Current Testing Baseline

Run before handoff or backup when code changes:

```bash
./.venv/bin/python -m pytest -q
```

Current expected result: `84 passed`.

For frontend-only edits, also run:

```bash
perl -0ne 'print $1 if /<script>(.*)<\/script>/s' app/static/index.html > /tmp/topotile-index-script.js
node --check /tmp/topotile-index-script.js
```

## User Preferences For This Project

- Implement directly when the request is concrete; do not stop at a proposal.
- Explain briefly in Chinese.
- Keep previously fixed behavior intact; the user explicitly worries about regressions.
- When modifying, update `CHANGELOG.md` with a concise timestamped entry.
- After code changes, restart the local server in a new Terminal shell and open `http://127.0.0.1:8000/` when useful.
- When asked for backup, do both local backup and GitHub push/tag.
