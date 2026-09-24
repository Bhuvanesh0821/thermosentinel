# data_pipeline/

Command-line entry points that reuse the backend services (`backend/app`). Run from the
repository root with the backend virtualenv (`backend/.venv/Scripts/python` on Windows,
`backend/.venv/bin/python` elsewhere).

| Command | What it does |
|---------|--------------|
| `python data_pipeline/pipeline.py check-sources` | Live check of FIRMS, Overpass, WorldCover and Neon - **no database needed**. |
| `python data_pipeline/pipeline.py migrate` | Apply migrations, register data sources, load the India boundary. |
| `python data_pipeline/pipeline.py facilities [--force]` | Ingest OSM industrial facilities over India's 30 tiles, 2 in parallel (~15 min for a first full load on public Overpass). Each tile is saved as it completes; re-runs only query tiles that never loaded, failed, or are older than `FACILITIES_REFRESH_HOURS` (`--force` re-queries all). |
| `python data_pipeline/pipeline.py firms [--backfill-days N]` | Ingest FIRMS detections (backfill only with a MAP_KEY). |
| `python data_pipeline/pipeline.py analyze` | Clustering → proximity → persistence → land cover → scoring → incidents/alerts. |
| `python data_pipeline/pipeline.py run [--facilities / --no-facilities]` | Full pipeline. |
| `python data_pipeline/pipeline.py retention` | Delete detections older than the retention window. |
| `python data_pipeline/pipeline.py status` | Row counts and latest runs. |
| `python data_pipeline/build_india_boundary.py` | Rebuild `database/boundaries/india_monitoring_area.geojson` (needs `pyshp`). |

The API's scheduler runs the same pipeline automatically; the CLI and the scheduler share a
database job lease, so they never run concurrently.
