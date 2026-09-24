# Stage 3 report - production hardening, deployment and demonstration readiness

Verified on **2026-09-24** against the deployed system. Everything below was tested on the live
URLs, not only compiled.

| | URL |
|---|---|
| Frontend (Vercel) | https://thermosentinel.vercel.app |
| Backend (Render, Docker, Singapore) | https://thermosentinel-api.onrender.com |
| API documentation | https://thermosentinel-api.onrender.com/api/docs |
| Source (public) | https://github.com/Bhuvanesh0821/thermosentinel |

## What Stage 3 added

| Area | Implementation |
|------|----------------|
| Environments | `APP_ENV=development|production`; production start-up refuses unsafe configuration (missing `DATABASE_URL`, weak/missing `ADMIN_API_TOKEN`, missing `FRONTEND_URL`, non-HTTPS or wildcard origins, non-live data mode). `FRONTEND_URL`/`BACKEND_URL` drive CORS, WebSocket origins and alert links. |
| Deployment | `render.yaml` Blueprint + `docker/backend.Dockerfile` (Python 3.14, pinned dependencies, 1 worker, `$PORT`, proxy headers, bounded graceful shutdown, small-instance tuning); `frontend/vercel.json` (SPA routing, immutable asset caching, security headers, microphone allowed for voice); `frontend/.env.production` with the public API URL - the production build fails without an HTTPS API URL. |
| Resilience | Background database retry at start-up (Neon cold starts) before the scheduler starts; redundant FIRMS downloads skipped after restarts; browser reconnects with exponential backoff, falls back to SSE while probing WebSocket, and refetches after every reconnect. |
| Observability | Structured JSON logs; failures counted per category (ingestion, external sources, database, API, alert generation, notifications, real-time) with secrets redacted, in `GET /api/system/health`. |
| Performance | Versioned response cache for map layers and analytics (invalidated by every data-changing event); cheaper risk-zone buffers; facilities generalised into clusters at national zoom; MapLibre worker pre-warming (first map paint ~10 s → ~4.6 s locally). |
| Demonstration test mode | `DATA_MODE=test-fixture` replays a recorded FIRMS sample (`source_mode='test_fixture'`) with a facility named "TEST FIXTURE …" on a separate `*_test` database; permanent TEST MODE banner; refused in production; a live API refuses a database containing fixture rows. Migration `0006`. |
| CI / operations | GitHub Actions CI (tests with a PostGIS service container + production build), keep-alive ping for the free Render tier. |
| Documentation | `README.md`, `ARCHITECTURE.md`, `DEPLOYMENT.md`, `API.md` (root) + methodology and data-source docs. |

## Final verification

### Backend
| Check | Result | Evidence |
|---|---|---|
| FastAPI starts | ✅ | Render service live; `/api/health` → `"status":"ok"`, `"environment":"production"` |
| Production server works | ✅ | Uvicorn (1 worker, proxy headers) in Docker on Render; security headers present; server header suppressed |
| Health check works | ✅ | Render health checks `/api/health`; `/api/system/health` reports 8/8 components connected, 0 failures |
| API endpoints work | ✅ | alerts, analytics, hotspots, facilities, investigation, voice, docs → HTTP 200 from the public URL; unknown resources → JSON 404; bad input → JSON 422; pipeline trigger without token → 403 |

### Database
| Check | Result | Evidence |
|---|---|---|
| Neon connection works | ✅ | PostgreSQL 18.6 / PostGIS 3.6.4, **6.9 ms** latency from Render (same region) |
| Migrations work | ✅ | 0001-0006 applied (0006 applied in production during Stage 3), checksummed |
| Data persists | ✅ | Detections from 2026-09-16 onwards retained across redeploys; 5,277 detections, 1,053 active clusters |

### Data
| Check | Result | Evidence |
|---|---|---|
| NASA FIRMS real data | ✅ | Production scheduler ingested the live FIRMS feed at 06:11 UTC (4,244 detections inside India in the current feed, 8,996 outside discarded); full cycle incl. analysis in 36 s |
| Industrial data | ✅ | 6,913 OpenStreetMap facilities (30/30 India tiles) |
| Land cover | ✅ | 153 ESA WorldCover samples in the production run, 0 errors |

### AI / analytics
| Check | Result | Evidence |
|---|---|---|
| Clustering, persistence, classification, intelligence | ✅ | 1,053 clusters, 102 persistent sources (64 industrial), 8 classes in use; e.g. INC-000006 Jindal Steel Works: persistent 7 of 9 days, inside footprint, score 77 with 10 explained factors |

### Alerts
| Check | Result | Evidence |
|---|---|---|
| Real alerts work | ✅ | 117 open alerts generated from real evidence (1 critical, 49 high, 67 medium) |
| Duplicate prevention | ✅ | Unit + integration tests; database partial unique index rejects a second open alert; re-running analysis in production created no duplicates |
| Notifications | ✅ | 117 in-app notifications (unread tracked); browser notifications opt-in; webhook/e-mail implemented but not configured (reported as "not configured") |
| Real-time stream | ✅ | `wss://…/ws/stream` and `/ws/alerts` accept the Vercel origin and reject others (403); SSE fallback works; during a production redeploy the open website went Live → reconnecting (06:20:01) → Live (06:20:03) automatically |

### Voice
| Check | Result | Evidence |
|---|---|---|
| Supported commands | ✅ | Production: "How many persistent thermal sources are active?" → "There are 102 active persistent thermal sources; 64 associated with mapped industrial facilities." |
| Unsupported commands fail safely | ✅ | "delete all alerts" → `supported: false`, no action |
| Microphone input | ⚠ not verified here | The development browser blocks microphone capture; to be checked in Chrome on the deployed HTTPS site (typed commands verified) |

### Frontend
| Check | Result | Evidence |
|---|---|---|
| Production build | ✅ | Vercel build from `main`; CI build job green |
| Map, dashboard, investigation, analytics, notifications | ✅ | Checked on https://thermosentinel.vercel.app with production data |
| Responsive layout | ✅ | Phone width (375 px): stacked KPIs, bottom navigation, collapsed map panels |
| Routing | ✅ | Deep links (e.g. `/investigation/6`) served by the SPA rewrite |

### Deployment
| Check | Result |
|---|---|
| Frontend deployed | ✅ Vercel |
| Backend deployed | ✅ Render (Singapore, free plan) |
| Neon connected | ✅ |
| Environment variables configured | ✅ `DATABASE_URL`, `FRONTEND_URL`, `BACKEND_URL` set in Render; `ADMIN_API_TOKEN` generated by Render; no secrets in the repository |
| Production API URL configured | ✅ `frontend/.env.production` → Render URL (verified in the deployed bundle) |
| Real-time connection verified | ✅ (see above) |

### Tests
* **121 passed, 0 skipped** locally (unit + PostGIS integration on a disposable `_test` database).
* GitHub Actions CI: backend (with a PostGIS 17 service container) and frontend jobs green.
* Dependency audits: `npm audit --omit=dev` 0 vulnerabilities; `pip-audit` on the pinned
  requirements: no known vulnerabilities.

## Security review

* No secrets in source, history, logs or the browser bundle (scanned; the public repository has no `.env`).
* Database URL, FIRMS key, admin token, SMTP/webhook credentials live only in the Render environment.
* CORS and WebSocket origins restricted to the Vercel URL in production; operator endpoints need
  `X-Admin-Token`; test-fixture endpoints do not exist in live mode.
* Errors are generic JSON (details only in server logs); inputs validated (types, ranges, enums, lengths).
* Dependencies pinned; `.gitignore` / `.dockerignore` exclude env files, virtualenvs, builds.

## Known limitations

* The Render free instance sleeps after 15 minutes without traffic; the GitHub keep-alive workflow
  (repository variable `BACKEND_URL`) keeps it awake, but GitHub may delay scheduled runs. A paid
  instance removes this.
* New alerts appear only when a real FIRMS cycle (hourly) produces qualifying evidence; none was
  produced between deployment and this report. The labelled test-fixture mode demonstrates the
  alert path on a separate test database if needed.
* Classifications are inferences, not ground truth; OSM coverage is uneven; persistence is limited
  by stored history.
