# ThermoSentinel architecture

ThermoSentinel turns satellite thermal detections into prioritised, explainable industrial
thermal intelligence for **India** (official-claim boundary + Exclusive Economic Zone). Every
record shown is real: NASA FIRMS detections, OpenStreetMap facilities, ESA WorldCover land cover.

## Production topology

```
                         ┌──────────────────────────── Browser ─────────────────────────────┐
                         │ React + Vite + MapLibre GL (Vercel, static, global CDN)           │
                         │  REST  https://<api>/api/*      live  wss://<api>/ws/alerts|stream │
                         │  (no secrets; only talks to the ThermoSentinel API)   SSE fallback │
                         └───────────────┬──────────────────────────────┬────────────────────┘
                                         │ HTTPS (CORS: FRONTEND_URL)   │ WSS (origin-checked)
                         ┌───────────────▼──────────────────────────────▼────────────────────┐
                         │ FastAPI on Render (Docker, Singapore, 1 uvicorn worker)            │
  GitHub Actions ──ping──▶  /api/health · REST routers · WebSocket + SSE · OpenAPI /api/docs   │
  (keep-alive, CI)       │  APScheduler (in-process): FIRMS → facilities (when due) → analysis │
                         │  response cache (invalidated by data events) · failure tracking     │
                         └───────┬───────────────────────┬──────────────────────┬─────────────┘
                                 │ TLS, pooled            │ HTTPS                │ HTTPS (COG ranges)
                   ┌─────────────▼───────────┐  ┌─────────▼──────────┐  ┌────────▼─────────────┐
                   │ Neon PostgreSQL 18      │  │ NASA FIRMS          │  │ ESA WorldCover (AWS) │
                   │ + PostGIS 3.6 (Singapore)│  │ OSM Overpass API    │  │ Nominatim (geocoding)│
                   └─────────────────────────┘  └─────────────────────┘  └──────────────────────┘
```

The API and the database are co-located in AWS ap-southeast-1 (Singapore), so each query is a
millisecond round trip instead of ~250 ms from a laptop in India.

## Data flow (real data end to end)

```
NASA FIRMS NRT ─▶ fetch ─▶ validate ─▶ clip to India+EEZ ─▶ thermal_observations (dedupe key)
OSM Overpass   ─▶ 6° tiles ─▶ classify thermal relevance ─▶ industrial_facilities (upsert)
                                   │
                                   ▼
 analysis: ST-DBSCAN clusters ─▶ PostGIS proximity ─▶ persistence ─▶ WorldCover land cover
           ─▶ features ─▶ intelligence score (10 factors) + rule-based classifier
           ─▶ incidents ─▶ alert rules (dedupe / escalate / auto-resolve) ─▶ notifications
                                   │
                                   ▼
            event bus ─▶ WebSocket /ws/alerts, /ws/stream, SSE /api/stream ─▶ UI refresh,
                                                                     toasts, browser alerts
```

## Repository layout

```
thermosentinel/
├── backend/app/
│   ├── main.py              app factory, lifespan (migrations, DB retry, scheduler, mode checks)
│   ├── config.py            typed settings from env / .env; production validation
│   ├── core/                errors, JSON envelopes, event bus, response cache, observability, audit
│   ├── db/                  engine (Neon-safe pooling), migration runner, run log, job leases
│   ├── geo/                 India boundary + EEZ, region sync, distances
│   ├── ingestion/           firms/ (Area API or public feed), facilities/ (Overpass), landcover/ (COG)
│   ├── analytics/           clustering, persistence, proximity, features, intelligence, classifier
│   ├── alerts/              rule engine (rules.py) + incident/alert lifecycle (service.py)
│   ├── notifications/       in-app, webhook, SMTP delivery (credentials server-side)
│   ├── voice/ search/ investigation/ health/ repositories/
│   ├── demo/fixture.py      labelled test-fixture replay (DATA_MODE=test-fixture, *_test DB only)
│   └── api/routes/          one router per resource, WebSockets (ws.py), SSE (stream.py)
├── database/migrations/     forward-only SQL 0001-0006 (checksummed) · boundaries/ (India area)
├── data_pipeline/           CLI: pipeline runs, source checks, boundary builder
├── frontend/                React/Vite UI · vercel.json · .env.production (public API URL)
├── ml/                      clustering sensitivity, feature export for future model training
├── tests/                   unit tests + PostGIS integration tests (disposable *_test database)
├── docker/                  backend.Dockerfile (Render), frontend.Dockerfile + nginx, compose
├── .github/workflows/       ci.yml (tests + build), keepalive.yml (Render free tier)
├── render.yaml              Render Blueprint (backend service, env var declarations)
├── README.md · ARCHITECTURE.md · DEPLOYMENT.md · API.md
└── docs/                    intelligence methodology, data sources, stage reports
```

## Runtime behaviour

* **Start-up**: production configuration is validated first (database URL, admin token,
  HTTPS frontend origin, live data mode); unsafe settings stop the deploy with a clear log line.
  Migrations are applied, the source registry upserted and the India boundary synced. If Neon
  is unreachable (e.g. a suspended compute waking up), the API still serves `/api/health` and
  retries the database every `DB_STARTUP_RETRY_SECONDS`, starting the scheduler once ready.
* **Ingestion**: every `FIRMS_POLL_MINUTES` (60) the scheduler runs FIRMS → facilities (only
  tiles older than `FACILITIES_REFRESH_HOURS`) → analysis, under a database job lease (no
  overlapping runs, even across instances). A cycle is skipped if FIRMS was fetched less than
  half an interval ago (restarts and wake-ups do not re-download). Detections are deduplicated
  by a unique source key; alerts by a partial unique index (one open alert per incident).
  Every run is recorded in `ingestion_runs` and `system_events`.
* **Real time**: pipeline steps and alert changes publish on an in-process bus, fanned out to
  WebSocket and SSE subscribers (20 s heartbeat). The browser reconnects with backoff and falls
  back from WebSocket to SSE; on reconnect it refetches the affected data.
* **Caching**: heavy read endpoints (map layers, analytics, boundary) are cached in memory and
  keyed on a data version that advances on every completed pipeline step or alert/operator
  action - never stale beyond the last change, with a 10-minute ceiling.
* **Observability**: structured JSON logs; failures in ingestion, external sources, database,
  API, alert generation, notifications and real-time connections are counted and summarised
  (with secrets redacted) in `GET /api/system/health`.
* **Shutdown**: streaming connections get 10 s to close; the scheduler stops; interrupted runs
  are closed as failed on the next start.

## Data modes

| Mode | Where | Data |
|------|-------|------|
| `live` (default, production) | Neon production database | Real FIRMS / OSM / WorldCover only. Refuses to start if any test-fixture row is present. |
| `test-fixture` (development only) | A separate database named `*_test` | A recorded FIRMS sample replayed with `source_mode='test_fixture'` and one facility named "TEST FIXTURE …". The UI shows a permanent TEST MODE banner. Refused in production. |

## Why these choices

* **PostGIS geography** gives metre-based `ST_DWithin` / `ST_Distance` with GIST indexes, so
  "nearest facility" and "detections within 1 km over 30 days" are single indexed queries.
* **ST-DBSCAN on a sparse neighbour graph** (haversine BallTree + time filter + scikit-learn
  DBSCAN, precomputed metric) scales with real neighbours, not N².
* **Rule-based, weighted evidence** rather than an opaque model: no labelled ground truth
  exists yet, so every result is explainable factor by factor (see
  `docs/intelligence-methodology.md`). The classifier interface allows a trained model later.
* **One API instance with an in-process scheduler** fits the free tier and keeps the design
  simple; the database lease makes it safe to scale out later.
* **Direct browser → API connection** (not a Vercel proxy): Vercel rewrites do not carry
  WebSockets, so the frontend uses `VITE_API_BASE_URL` and the API allow-lists `FRONTEND_URL`.
