# TopoTile Studio

## Overview / 简介

TopoTile Studio is a local web app that turns OpenStreetMap data and optional elevation data into 3D-printable city and terrain tiles. It is designed for practical desktop 3D printing workflows: select an area on the map, choose layers and road detail, generate a preview, then download slicer-friendly `.3mf`, `.glb`, `.stl`, or numbered chunk exports.

TopoTile Studio 是一个本地运行的网页工具，可以把 OpenStreetMap 地图数据和可选地形高程数据生成适合 3D 打印的城市/地形模型。它面向桌面 3D 打印流程设计：在地图上选择区域，调整建筑、道路、水体、绿地、停车场和地形选项，生成预览后下载适合切片软件使用的 `.3mf`、`.glb`、`.stl` 或分块编号文件。

Key features / 主要功能：

- Interactive map selection with free, fixed-ratio, circle, and hexagon modes / 支持自由比例、固定比例、圆形和正六边形选区
- OSM buildings, roads, water, green areas, and outdoor surface parking / 支持 OSM 建筑、道路、水体、绿地和室外露天停车场
- Automatic terrain relief, DEM upload, and large-map terrain tile mode / 支持自动地形、DEM 上传和大型地图地形瓦片模式
- Water cutout mode for hollow water areas / 支持水体镂空模式，便于下方放置蓝色纸片或材料
- Road-level selection, road cleanup presets, and separate footway/pedestrian widths / 支持道路级别选择、道路清理强度和步行道路独立宽度
- Printability score, project save/load, cache cleanup, custom filenames, and numbered chunk exports / 支持可打印性评分、项目保存/加载、清理缓存、自定义文件名和分块编号导出

A local web app for generating 3D-printable city and terrain models from OpenStreetMap vector data and an optional DEM GeoTIFF.

The first target is Bambu Lab A1 printing: the app exports a standard `.3mf` file with separate objects for terrain, buildings, roads, water, green areas, and surface parking lots, plus a `.glb` preview file.

## What this version does

- Runs locally at `http://127.0.0.1:8000`
- Includes address/place search that moves the current map selection to the search result
- Lets you choose an area by dragging/resizing a map selection in free, 1:1, 5:7, 7:5, circle, or regular-hexagon modes, or by entering a bbox
- Lets you select OSM road levels before generating the model
- Provides road cleanup presets for quickly switching between detailed and cleaner printable road networks
- Can automatically add terrain relief from free 90 m elevation data, or use an uploaded DEM GeoTIFF
- Includes Large Map Mode, which internally chunks OSM requests and uses cached terrain tiles while still exporting one complete `.3mf`
- Lets you include outdoor surface parking lots as a very thin printable layer
- Can cut water bodies out of the base, leaving through-holes for placing colored paper or acrylic underneath
- Scores printability before printing and reports common risks such as thin bases, dense meshes, high relief, and narrow roads
- Supports project save/load JSON files
- Supports custom export filenames
- Supports numbered chunk export with a ZIP bundle and manifest
- Includes cache status and cleanup controls for generated jobs and terrain tiles
- Downloads OSM features through Overpass API
- Supports closed OSM water ways, water multipolygon relations, and coastline-derived ocean water when coastline data crosses the selection
- Accepts an optional DEM GeoTIFF upload for terrain relief; uploaded DEMs override auto terrain
- Generates a watertight terrain base
- Extrudes buildings from OSM footprints
- Converts roads, water, green areas, and surface parking lots into thin printable layers, or cuts water through the base when `Cut out water` is enabled
- Exports slicer-compatible `.3mf`, `.glb`, `.stl`, and `ATTRIBUTION.txt`
- Stores generated jobs locally under `data/jobs/` and `data/outputs/`

## Current limits

- OSM relation multipolygons are not fully reconstructed yet. Closed ways are supported well.
- Water multipolygon relations are supported, but very large water bodies only appear when their relation boundary or coastline data is available in the selected area.
- Normal auto terrain relief uses 90 m elevation data, so small curbs, stairs, and building-scale grade changes are not captured. Large Map Mode uses cached terrain GeoTIFF tiles instead.
- Large Map Mode removes the Open-Meteo per-minute elevation bottleneck, but public Overpass OSM requests can still be slow for very dense 10 km+ city areas.
- Terrain-following feature layers are simplified. Buildings and surface layers use local sampled terrain height near their centroid.
- Very large areas can be slow or too dense. Start with 0.5–2 km².

## Install

Python 3.11 or 3.12 is recommended.

```bash
cd osm_dem_3mf_modeler
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run local web app

On macOS, you can double-click:

```text
Open_OSM_DEM_3MF_Modeler.command
```

The launcher checks dependencies, starts the local server, and opens the browser.

You can also run it manually:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Generate a sample without internet

This creates a synthetic `.3mf` and `.glb` so you can test Bambu Studio import immediately.

```bash
python scripts/generate_sample.py
```

Outputs go to:

```text
data/outputs/sample/
```

## Bambu A1 defaults

The UI defaults to:

- Maximum XY size: 180 mm
- Maximum allowed XY size: 240 mm
- Base thickness: 3 mm
- Building max height: 45 mm
- Minimum road width: 0.8 mm
- Footway width: 0.60 mm
- Pedestrian width: 0.60 mm
- Bridge clearance: 2.5 mm when `Cut out water` needs a road to span a water cutout
- Road levels: motorway, trunk, primary, secondary, tertiary, unclassified, residential, living street, pedestrian, and footway. Smaller service roads, steps, cycleways, tracks, and paths are available but off by default.

These values are intentionally print-oriented rather than purely geographically accurate.

## Data and attribution

Generated models should include attribution for the data sources used.

For OSM data, the app writes:

```text
Data © OpenStreetMap contributors, available under the Open Database License.
```

The app uses public Overpass API instances for OpenStreetMap feature downloads. Normal use does not require an API key or registration. If a public Overpass server rejects a request, shrink the selection area or retry later.

If you upload a DEM, add the DEM source attribution in the UI field before generating.

If you enable auto terrain relief, the app uses Open-Meteo Elevation API data based on Copernicus DEM GLO-90. Open-Meteo does not require an API key for this normal local use.

If you enable Large Map Mode, the app uses Mapzen/AWS Terrain Tiles for elevation and stores them under `data/cache/terrain_tiles/`.

## Suggested workflow

1. Start the app.
2. Zoom the map to a small city area.
3. Click `Use current map view`.
4. Keep the model size around 120–180 mm for the first print.
5. Optionally upload a DEM GeoTIFF.
6. Generate the job.
7. Download `.3mf`.
8. Open in Bambu Studio.
9. Assign colors/materials to separate objects if desired.
