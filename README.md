# ThermoSentinel

**AI-enabled geospatial industrial thermal intelligence for India** - Smart India Hackathon prototype.

ThermoSentinel ingests real NASA FIRMS satellite thermal detections, OpenStreetMap industrial
infrastructure and ESA WorldCover land cover; clusters detections in space and time; relates them
to refineries, flares, steel plants, power stations and mines with PostGIS; measures persistence;
and produces explainable, prioritised assessments (gas-flare-like activity, persistent industrial
source, mining-associated, industrial-associated, agricultural or vegetation fire, …). A rule
engine raises alerts from that evidence and streams them in real time to a GIS command-centre UI
with notifications, voice commands and an investigation workspace.

* **Real data only** - no synthetic detections, facilities, alerts or statistics. Empty, error and
  "no data stored" states are shown explicitly.
* **India only** - every record is clipped to India's officially claimed boundary (incl. all of
  Jammu & Kashmir, Ladakh and Arunachal Pradesh) plus its Exclusive Economic Zone.
* **Explainable** - every score is broken down factor by factor; classifications are a transparent
  rule-based baseline (no trained model is claimed).

| Document | Contents |
|----------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Topology, data flow, folder structure, runtime behaviour, design choices |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Vercel + Render + Neon production deployment, keep-alive, operations |
| [API.md](API.md) | Every endpoint, envelopes, error codes, real-time streams |
| [docs/intelligence-methodology.md](docs/intelligence-methodology.md) | Clustering, persistence, score, classifier, alert rules |
| [docs/data-sources.md](docs/data-sources.md) | Sources, India boundary, licences, provenance |
| [docs/stage-2-report.md](docs/stage-2-report.md) · [docs/stage-1-report.md](docs/stage-1-report.md) | Verification reports |

---

## Architecture in one picture

```
 NASA FIRMS ─┐                         ┌─────────────── Render (Singapore) ───────────────┐
 OSM Overpass├──▶ server-side ingestion│ FastAPI · scheduler · clustering · intelligence  │
 WorldCover ─┘   (no keys in browser)  │ alert engine · WebSocket/SSE · /api/health       │
                                       └───────┬──────────────────────────────▲───────────┘
                                               │ PostGIS SQL                  │ HTTPS / WSS
                                   ┌───────────▼────────────┐   ┌─────────────┴─────────────┐
                                   │ Neon PostgreSQL+PostGIS│   │ Vercel: React + MapLibre  │
                                   │ (Singapore)            │   │ command-centre UI         │
                                   └────────────────────────┘   └───────────────────────────┘
```

## Technology stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, Vite 8, React Router 7, MapLibre GL 6, lucide-react, Inter + IBM Plex Mono, CSS modules with design tokens |
| Basemaps | OpenFreeMap (vector, OpenMapTiles), EOX Sentinel-2 cloudless (satellite hybrid), NASA GIBS VIIRS |
| Backend | Python 3.14, FastAPI, Uvicorn, Pydantic Settings, SQLAlchemy 2 Core + psycopg 3, APScheduler, httpx |
| Analytics | pandas, NumPy, scikit-learn (ST-DBSCAN), Shapely, rasterio (Cloud-Optimised GeoTIFF reads) |
| Database | Neon PostgreSQL 18 + PostGIS 3.6 (geography columns, GIST indexes, forward-only SQL migrations) |
| Real time | WebSockets (`/ws/stream`, `/ws/alerts`) with Server-Sent Events fallback (`/api/stream`) |
| Hosting | Vercel (frontend), Render Docker web service (API), Neon (database), GitHub Actions (CI, keep-alive) |

## System requirements

* Python **3.13+** (tested on 3.14.3), Node.js **20+** (tested on 24), git.
* A free **Neon** account; optionally a free **NASA FIRMS MAP_KEY**.
* ~1 GB RAM for the API (the Render free instance has 512 MB and is tuned for it).

---

## 1. Local setup

```bash
git clone https://github.com/<you>/thermosentinel.git && cd thermosentinel
cp .env.example .env            # then set DATABASE_URL (and optionally NASA_FIRMS_MAP_KEY)

# Backend
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt   # Windows
# backend/.venv/bin/python   -m pip install -r backend/requirements-dev.txt   # Linux / macOS

# Frontend
cd frontend && npm ci && cd ..
```

## 2. Neon PostgreSQL setup

1. In the Neon console create a **new project** for ThermoSentinel (keep other projects separate -
   free-plan limits are per project) in **AWS Asia Pacific (Singapore)**, next to where the API
   runs. A project's region cannot be changed later.
2. **Connect** → choose the **pooled** connection → copy the string
   (`postgresql://…-pooler….neon.tech/neondb?sslmode=require`).
3. Put it in `.env` as `DATABASE_URL=…` (never in code, chat or commits). PostGIS is enabled by the
   first migration - nothing to do in the console.

## 3. NASA FIRMS setup (optional but recommended)

Request a MAP_KEY at https://firms.modaps.eosdis.nasa.gov/api/map_key/ and set
`NASA_FIRMS_MAP_KEY` in `.env` (locally) or in the Render dashboard (production).

* **With a key**: FIRMS Area API over India's extent, 1-5 days per request, 10-day backfill on the
  first run.
* **Without a key**: FIRMS' public near-real-time CSV feed (South Asia, last 7 days) - also real NASA
  data - clipped to India. The source mode is recorded on every row and shown in the UI.

The key is only ever used server-side; it is masked in logs and never sent to the browser.

## 4. Environment variables

All variables are documented in [`.env.example`](.env.example) (backend) and in `render.yaml`
(production). Secrets are marked **secret**; nothing secret is ever committed.

| Variable | Where | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | backend, **secret** | Neon pooled connection string |
| `APP_ENV` | backend | `development` / `production` (production validates config at start-up) |
| `FRONTEND_URL` | backend (production) | Public frontend URL - allowed browser origin for CORS and WebSockets; used in alert links |
| `BACKEND_URL` | backend (production) | Public API URL |
| `CORS_ORIGINS` | backend | Extra allowed origins (comma-separated). Local dev defaults to `localhost:5173/4173` |
| `ADMIN_API_TOKEN` | backend, **secret** | Protects operator endpoints (`X-Admin-Token`); required in production (≥ 24 chars) |
| `NASA_FIRMS_MAP_KEY` | backend, **secret**, optional | FIRMS Area API key |
| `FIRMS_POLL_MINUTES` | backend | Ingestion + analysis cadence (default 60) |
| `SCHEDULER_ENABLED`, `AUTO_MIGRATE` | backend | Background jobs / migrations at start-up |
| `INCIDENT_MIN_SCORE`, `ALERT_MIN_PRIORITY`, `ALERT_RULE_*`, `ALERT_RULES_DISABLED` | backend | Incident threshold, alert rules |
| `NOTIFY_WEBHOOK_URL`, `NOTIFY_WEBHOOK_MIN_SEVERITY` | backend, **secret**, optional | Webhook alerts |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`, `NOTIFY_EMAIL_TO`, `NOTIFY_EMAIL_MIN_SEVERITY` | backend, **secret**, optional | E-mail alerts |
| `GEOCODER_ENABLED`, `GEOCODER_URL` | backend | Place search / "zoom to <place>" (Nominatim, results clipped to India) |
| `CLASSIFIER` | backend | `rules` (the only registered classifier) |
| `DATA_MODE` | backend | `live` (default) or `test-fixture` (development only, see §11) |
| `OBSERVATION_RETENTION_DAYS` | backend | Keeps storage inside the Neon free tier |
| `VITE_API_BASE_URL` | frontend build | Public API URL (`frontend/.env.production`); not a secret |
| `VITE_API_SAME_ORIGIN` | frontend build | `true` when `/api` and `/ws` are proxied on the same origin (local preview, nginx) |

## 5. Database migration

Migrations (`database/migrations/0001…0006`) run automatically when the API starts
(`AUTO_MIGRATE=true`); they are forward-only and checksummed. To run them explicitly:

```bash
backend/.venv/Scripts/python data_pipeline/pipeline.py migrate
```

## 6. Start the backend

```bash
backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

* API docs: http://127.0.0.1:8000/api/docs · health: http://127.0.0.1:8000/api/health
* With `SCHEDULER_ENABLED=true` the first ingestion + analysis cycle starts ~20 s after start-up and
  repeats every `FIRMS_POLL_MINUTES`. The first facility load covers India in 30 Overpass tiles
  (~15 minutes on public servers), saved tile by tile and resumable.
* Or run the pipeline yourself: `backend/.venv/Scripts/python data_pipeline/pipeline.py run`

## 7. Start the frontend

```bash
cd frontend
npm run dev                          # http://localhost:5173 (proxies /api and /ws to 127.0.0.1:8000)
npm run build:local && npm run preview   # local production build on http://localhost:4173
```

`npm run build` is the production build and requires `VITE_API_BASE_URL` (set in
`frontend/.env.production`); it fails on purpose without it. The browser never receives any
credential.

## 8. Production deployment

Frontend on **Vercel**, API on **Render** (Docker, Singapore), database on **Neon**, CI and
keep-alive on **GitHub Actions** - step by step in [DEPLOYMENT.md](DEPLOYMENT.md). In short:

1. Push to GitHub → Render **New → Blueprint** (reads `render.yaml`) → enter `DATABASE_URL`,
   `FRONTEND_URL`, `BACKEND_URL` → deploy.
2. Vercel → import the repository with root directory `frontend` → deploy.
3. GitHub → repository variable `BACKEND_URL` for the keep-alive workflow.

## 9. Real-time configuration

* The browser opens `wss://<API>/ws/stream` (derived from `VITE_API_BASE_URL`). If WebSockets are
  blocked it falls back to SSE (`/api/stream`) and keeps probing for WebSocket; after any
  reconnect it refetches, so events missed while disconnected are not lost.
* The API accepts WebSocket connections only from `FRONTEND_URL` / `CORS_ORIGINS` (others: 403).
* Heartbeats every 20 s keep connections open through proxies. Behind your own nginx, use the
  `/ws/` block in `docker/nginx.conf` (Upgrade headers, long read timeout).

## 10. Notification configuration

| Channel | How to enable |
|---------|---------------|
| In-app notification centre | Always on (unread count, details, mark read, open investigation) |
| Browser notifications | Settings → Notifications → *Enable browser notifications* (per device, asks permission) |
| Webhook (Slack/Teams/automation) | `NOTIFY_WEBHOOK_URL`, `NOTIFY_WEBHOOK_MIN_SEVERITY` |
| E-mail | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `NOTIFY_EMAIL_TO`, `NOTIFY_EMAIL_MIN_SEVERITY` |

Only real alerts are notified; each alert event (created / escalated) is delivered once per channel
and recipient. Channels without credentials report *not configured* and send nothing.

## 11. Voice configuration

Voice uses the browser's Web Speech API (Chrome or Edge; speech is transcribed by the browser's
speech service, which needs internet access). No API key or server credential is involved.
Allow the microphone for the site when asked; typing a command in the same panel works everywhere.
Supported commands include:

* "Show active thermal anomalies" · "Show high priority industrial incidents"
* "How many persistent thermal sources are active?" · "Show incidents near power plants"
* "Open the latest alert" · "Zoom to the latest industrial thermal event" · "Zoom to Jamnagar"

The interpreter maps speech to one whitelisted action; anything else is answered with
"not supported" and suggestions - nothing is executed.

### Test-fixture mode (development only)

If no qualifying live alert happens during a demonstration, a clearly labelled test mode can
show the full alert path. It never touches live data:

```bash
# a separate local database whose name ends in _test
DATA_MODE=test-fixture DATABASE_URL=postgresql://postgres@127.0.0.1:55432/thermosentinel_test \
  backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8000
```

Settings → Data sources → **Replay test fixture** replays a recorded NASA FIRMS sample (tagged
`source_mode='test_fixture'`) next to a facility named "TEST FIXTURE refinery (not a real site)";
the alert engine raises an alert that streams to the UI. A **TEST MODE** banner is shown on every
page. The API refuses this mode in production or on a database not named `*_test`, and a live API
refuses to start on a database that contains fixture rows.

## 12. SIH demonstration flow (live data)

1. Open the Vercel URL → **Dashboard**: top bar shows **Live**; KPI strip shows real counts.
2. Bottom strip / **Settings → System health**: every data source and component status.
3. Map (satellite hybrid): live FIRMS detections (colour = FRP), clusters, incidents, risk zones.
4. Layers → *Industrial facilities* (6,900+ OSM sites, clustered at national scale).
5. Click a thermal event → detail panel → **Investigate**.
6. Investigation page: facility footprint and distance, persistence (days detected), detection
   history, classification rationale and rejected alternatives, 10 intelligence factors,
   alert history, timeline and provenance.
7. **Alerts**: open alerts with the rules that fired; expand for measured values vs thresholds.
8. Notification bell → open a notification → investigation. New alerts arrive live as toasts
   when an ingestion cycle produces qualifying evidence (hourly).
9. Voice: mic button → "Show high priority industrial incidents".
10. **Analytics**: detections per day, FRP trend, industrial share, incidents by priority,
    geographic distribution; each chart has a table view.
11. **Settings**: data sources and pipeline runs, notification channels, alert rules, model.

## 13. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Top bar "API offline" | API not running or `VITE_API_BASE_URL` wrong. Check `<API>/api/health`. On Render free, the first request after sleep takes ~1 min. |
| "Stream reconnecting" | WebSocket origin not allowed: set `FRONTEND_URL` exactly (scheme, no trailing slash). `/api/system/health` → failures → realtime shows rejected origins. |
| Render deploy fails "Refusing to start in production" | The log names the missing setting (e.g. `FRONTEND_URL`, `ADMIN_API_TOKEN`). |
| `database_unavailable` | Neon compute waking or wrong `DATABASE_URL`; the API retries every 60 s automatically. |
| Map blank | Basemap host blocked by a network filter; data layers still load on the fallback background. |
| Facility layer empty | First OSM load still running (Settings → Data sources shows tile progress). |
| `npm run build` fails asking for `VITE_API_BASE_URL` | Intended: set it in `frontend/.env.production`, or use `npm run build:local` for a same-origin build. |
| Voice button says microphone blocked | Allow the microphone for the site, or type the command. |

## 14. Useful commands

```bash
backend/.venv/Scripts/python data_pipeline/pipeline.py check-sources   # live source check (no DB needed)
backend/.venv/Scripts/python data_pipeline/pipeline.py status          # DB counts + latest runs
backend/.venv/Scripts/python -m pytest                                 # unit tests (from repo root)
# + PostGIS integration tests on a disposable database whose name ends in _test:
# TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/thermosentinel_test backend/.venv/Scripts/python -m pytest
```

## 15. Limitations

* Classifications are inferred from satellite heat plus open data; nothing is ground-verified.
* OSM facility coverage in India is uneven: "no facility nearby" can mean "not mapped".
* Persistence is bounded by stored history (the keyless FIRMS feed starts with 7 days).
* FIRMS detects fires ≥ ~375 m pixels (VIIRS) / 1 km (MODIS) at overpass times only.
* Render free instances sleep when idle; the keep-alive workflow mitigates this but GitHub may
  delay scheduled runs. Real-time events are per API instance.
* Natural Earth 1:10m boundary accuracy is about 1 km near international borders.

## 16. Data provenance and attribution

Thermal detections: NASA FIRMS (LANCE) - VIIRS S-NPP / NOAA-20 / NOAA-21 and MODIS. Facilities:
© OpenStreetMap contributors (ODbL) via the Overpass API. Land cover: © ESA WorldCover project
2021 / Copernicus Sentinel data (CC BY 4.0). India boundary: Natural Earth (public domain, India
point of view). EEZ: Flanders Marine Institute, Marine Regions (CC BY 4.0). Basemaps: OpenFreeMap /
OpenMapTiles (© OpenStreetMap), EOX Sentinel-2 cloudless 2021 (CC BY-NC-SA 4.0), NASA GIBS.
Geocoding: OSM Nominatim. Every record stores its source, run and timestamp; see `/api/data-sources`.
