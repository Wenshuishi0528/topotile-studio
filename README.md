# TopoTile Studio / 3D地图工坊

把真实地图生成可 3D 打印的城市与地形模型。

Turn real maps into 3D-printable city and terrain models.

<img width="2444" height="2108" alt="截屏2026-06-30 23 48 52" src="https://github.com/user-attachments/assets/b2975ad5-9beb-4719-9956-50dcbf902c56" />


**Status:** Beta / Preview

**License:** Source-available under CC BY-NC-SA 4.0. Personal, educational,
research, and other non-commercial use only.

**Author:** Made by Wenshuishi

TopoTile Studio / 3D地图工坊 is not an OSI-approved open-source project. It is a
source-available non-commercial project. Commercial use, resale, paid hosting,
or paid derivative products require separate written permission from the author.

TopoTile Studio / 3D地图工坊 目前是 Beta / Preview 版本。本项目源码公开，但仅限个人、学习、
研究和其它非商业用途使用。禁止商业使用、转售、付费部署或作为付费衍生产品提供；
如需商业授权，请另行联系作者。

## Overview / 简介

TopoTile Studio / 3D地图工坊 is a local web app that turns OpenStreetMap data and optional elevation data into 3D-printable city and terrain models. It is designed for practical desktop 3D printing workflows: select an area on the map, choose layers and road detail, generate a preview, then download slicer-friendly `.3mf`, `.glb`, `.stl`, or numbered chunk exports.

3D地图工坊是一个本地运行的网页工具，可以把 OpenStreetMap 地图数据和可选地形高程数据生成适合 3D 打印的城市/地形模型。它面向桌面 3D 打印流程设计：在地图上选择区域，调整建筑、道路、水体、绿地、停车场和地形选项，生成预览后下载适合切片软件使用的 `.3mf`、`.glb`、`.stl` 或分块编号文件。

Key features / 主要功能：

- Interactive map selection with free, fixed-ratio, circle, and hexagon modes / 支持自由比例、固定比例、圆形和正六边形选区
- OSM buildings, roads, water, green areas, outdoor surface parking, and airport pavement / 支持 OSM 建筑、道路、水体、绿地、室外露天停车场和机场跑道/滑行道硬化面
- Default Overture Maps building supplement for areas where OSM footprints are missing / 默认使用 Overture Maps 补充 OSM 缺失建筑轮廓
- Automatic terrain relief, DEM upload, and large-map terrain tile mode / 支持自动地形、DEM 上传和大型地图地形瓦片模式
- Water cutout mode for hollow water areas / 支持水体镂空模式，便于下方放置蓝色纸片或材料
- Road-level selection, road cleanup presets, and separate footway/pedestrian widths / 支持道路级别选择、道路清理强度和步行道路独立宽度
- Printability score, project save/load, cache cleanup, custom filenames, and numbered chunk exports / 支持可打印性评分、项目保存/加载、清理缓存、自定义文件名和分块编号导出
- Cancellable generation jobs for stopping long OSM/terrain downloads or exports / 支持终止正在运行的生成任务，停止长时间 OSM/地形下载或导出

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
- Includes cache status and cleanup controls for generated jobs, OSM downloads, Open-Meteo elevation samples, and terrain tiles
- Can stop the current generation job; completed cache entries are kept for reuse
- Supports English and Chinese UI switching
- Can export raised GPX/KML route tracks over terrain
- Automatically applies common mesh repair before export
- Downloads OSM features through Overpass API
- Adds Overture Maps building footprints by default when the selected area has gaps in OSM building data; OSM buildings remain primary and overlapping Overture footprints are skipped
- Supports closed OSM water ways, water multipolygon relations, supplemental large-area water-boundary fetching, and coastline-derived ocean water when coastline data crosses the selection
- Supports airport runways, taxiways, and aprons as a low printable pavement layer
- Accepts an optional DEM GeoTIFF upload for terrain relief; uploaded DEMs override auto terrain
- Generates a watertight terrain base
- Extrudes buildings from OSM footprints
- Converts roads, water, green areas, and surface parking lots into thin printable layers, or cuts water through the base when `Cut out water` is enabled
- Exports slicer-compatible `.3mf`, `.glb`, `.stl`, and `ATTRIBUTION.txt`
- Stores generated jobs locally under `data/jobs/` and `data/outputs/`

## Current limits

- This is a Beta tool. It is useful, but not guaranteed to handle every map area or slicer edge case.
- Large map selections can still hit public Overpass API rate limits or timeouts. Use smaller areas, caching, or self-hosted/third-party OSM services for heavy use.
- OSM data completeness depends on local mapping quality. Missing OSM buildings can often be supplemented from Overture Maps; missing roads, water, or green areas cannot always be recovered automatically.
- Overture supplemental building data is used as a fallback footprint source, not a guarantee of complete or survey-grade building geometry.
- Water multipolygon relations and large water bodies are supported better than before, but extremely complex or incomplete OSM relations may still fail.
- Normal auto terrain relief uses 90 m elevation data, so small curbs, stairs, and building-scale grade changes are not captured. Large Map Mode uses cached terrain GeoTIFF tiles instead.
- Terrain-following feature layers are simplified for printability.
- Automatic mesh repair reduces common non-manifold issues, but does not guarantee every generated file is printable in every slicer.
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

The launchers check for a compatible Python 3.11/3.12 runtime. If it is
already installed, they create/update the local virtual environment and start
the web app. If it is missing, they ask `yes` or `no` before trying an automatic
install.

启动文件会先检查是否有可用的 Python 3.11/3.12。如果已经安装，就会自动创建/更新本地虚拟环境并启动网页。
如果没有检测到合适版本，会先询问 `yes` 或 `no`，得到确认后才会尝试自动安装。

On macOS, you can double-click:

```text
A-Start-MacOS-TopoTile_Studio(macOS点这个启动).command
```

If Python 3.11/3.12 is missing on macOS, the launcher can install Python 3.12
through Homebrew after confirmation. If Homebrew is missing, it asks before
installing Homebrew. The Homebrew installer may ask for your Mac password.

如果 macOS 缺少 Python 3.11/3.12，启动器可以在确认后通过 Homebrew 安装 Python 3.12。
如果没有 Homebrew，会先询问是否安装 Homebrew。Homebrew 安装程序可能会要求输入 Mac 密码。

On Windows, you can double-click:

```text
A-Start-Windows-TopoTile_Studio(Windows点这个启动).bat
```

If Python 3.11/3.12 is missing on Windows, the launcher can install Python 3.12
with `winget` after confirmation. If `winget` is unavailable or installation
fails, it opens the official Python download page.

如果 Windows 缺少 Python 3.11/3.12，启动器可以在确认后通过 `winget` 安装 Python 3.12。
如果没有 `winget` 或安装失败，会打开 Python 官方下载页面。

You can also run it manually:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Generate the built-in offline test model without internet

This creates the bundled `.3mf`, `.glb`, `.stl`, and project JSON so you can test Bambu Studio import immediately without OSM/API access.

```bash
python scripts/generate_sample.py
```

On macOS, you can also double-click:

```text
A-Test_Offline(离线测试).command
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

The app uses public Overpass API instances for OpenStreetMap feature downloads. Normal use does not require an API key or registration. Successful OSM responses are cached under `data/cache/osm/`; if a public Overpass server rejects a request, shrink the selection area or retry later.

When buildings are enabled, the app also tries to supplement missing building
footprints from Overture Maps Foundation's buildings dataset. OSM buildings stay
primary: Overture footprints that overlap existing OSM buildings are skipped.
Successful Overture building batches are cached under
`data/cache/osm/overture_buildings/` and are cleared with the OSM cache.

如果开启建筑图层，程序会默认尝试用 Overture Maps Foundation 的建筑数据补充 OSM
缺失的建筑轮廓。OSM 建筑优先；与已有 OSM 建筑重叠的 Overture 轮廓会被跳过。
成功下载的 Overture 建筑批次会缓存到
`data/cache/osm/overture_buildings/`，清理 OSM 缓存时会一并清理。

Public OpenStreetMap ecosystem services are not unlimited commercial backends.
For heavy use, reduce request frequency, keep cache enabled, use third-party
providers, or self-host the required services.

If you upload a DEM, add the DEM source attribution in the UI field before generating.

If you enable auto terrain relief, the app uses Open-Meteo Elevation API data based on Copernicus DEM GLO-90. Open-Meteo does not require an API key for this normal local use. Successful elevation batches are cached under `data/cache/elevation/open_meteo/`.

If you enable Large Map Mode, the app uses Mapzen/AWS Terrain Tiles for elevation and stores them under `data/cache/terrain_tiles/`.

See also:

- `NOTICE.md` for license, attribution, public API usage, and third-party-name notices.
- `DISCLAIMER.md` for model accuracy, printability, and data-completeness disclaimers.
- OpenStreetMap copyright: https://www.openstreetmap.org/copyright
- OSMF attribution guidelines: https://osmfoundation.org/wiki/Licence/Attribution_Guidelines
- Overture Maps attribution: https://docs.overturemaps.org/attribution/
- OSM tile usage policy: https://operations.osmfoundation.org/policies/tiles/
- Nominatim usage policy: https://operations.osmfoundation.org/policies/nominatim/

## License / 许可证

This repository is source-available under the Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 International License
(CC BY-NC-SA 4.0).

本仓库源码公开，按 CC BY-NC-SA 4.0 授权，仅允许非商业用途。

You may use, study, modify, and share the project for personal, educational,
research, and other non-commercial purposes. If you share a modified version or
derivative, it must be shared under the same license and include the
corresponding modified source files.

你可以为了个人、学习、研究和其它非商业目的使用、学习、修改和分享本项目。如果你公开分享修改版或衍生版本，
必须使用相同许可证，并公开对应的修改后源码。

Commercial use, resale, paid hosting, paid derivative products, or using a
modified version as a commercial service are not permitted without separate
written permission from the author.

未经作者另行书面授权，禁止商业使用、转售、付费部署、作为付费衍生产品提供，
或将修改版作为商业服务提供。

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
