# Stage 2 report - intelligence, alerts, real-time, voice and the command-centre UI

Verified on **2026-09-24** against the project's Neon PostgreSQL 18.6 + PostGIS 3.6.4 database
(AWS ap-southeast-1) with live NASA FIRMS data. Nothing is deployed yet (Stage 3).

## What Stage 2 added

| Area | Implementation |
|------|----------------|
| Intelligence v2 (`ts-intel-2.0`) | 10 explainable factors incl. thermal intensity (brightness), observation frequency, spatial concentration; missing evidence excluded and weights renormalised. API returns `intelligence_score`, `risk_level`, factors, evidence. |
| Classification framework | `Classifier` interface; `RuleBasedClassifier` (`ts-rules 2.0`) with 8 hedged classes, rationale and rejected alternatives. Reported as a rule-based baseline, `trained_model: false`. |
| Alert engine | 6 configurable rules (`ALERT_RULE_*`), severity escalation (critical needs a facility link), one alert per incident (code + partial unique index), update / escalate / auto-resolve, stored evidence (measured value vs threshold). Migration `0005_alert_engine.sql`. |
| Notifications | In-app centre (unread count, details, mark read, investigate), browser notifications (with permission), webhook and SMTP e-mail (env credentials, server-side), one delivery per alert event and channel. |
| Real time | WebSockets `/ws/stream` and `/ws/alerts` (origin-checked, 20 s heartbeat) plus the SSE fallback `/api/stream`. |
| Voice / commands | Browser speech-to-text, typed fallback, server-side whitelisted interpreter; the interpreted command is shown; unsupported requests return `supported: false`. |
| UI | React Router sections `/dashboard /incidents /alerts /facilities /thermal-sources /investigation/:id /analytics /settings`; shared filters (time, severity, event type, facility type, persistence, confidence, area); global search (facilities, incidents, alerts, places); Google-style satellite-hybrid and road basemaps limited to India's official boundary + EEZ. |
| Analytics | `/api/analytics/overview` and `/api/analytics/grid`: detections per day (day/night), FRP median/p90, industrial-associated detections, incidents by priority, geographic grid, classification / facility-type / persistence mixes, top persistent sources. Each chart has a table view; days without stored FIRMS data are hatched, never drawn as zero. |
| System health | `/api/system/health`: API, database, FIRMS, OSM facilities, land cover, real-time stream, notification service, scheduler → connected / degraded / unavailable. |

## Completion checklist

| # | Requirement | Result | Evidence |
|---|-------------|--------|----------|
| 1 | Real NASA data flows through the entire pipeline | ✅ | Pipeline run on Neon: FIRMS public NRT feed → 5,276 detections inside India stored (history from 2026-09-16), 135 new in the verification run; 9,830 outside-India rows discarded. |
| 2 | Real industrial facilities are displayed | ✅ | 6,913 OSM facilities (30/30 India tiles) on the map, Facilities page and investigation footprints (e.g. Jindal Steel Works, OSM way/119390670, 514 ha). |
| 3 | Events are clustered | ✅ | 1,052 active ST-DBSCAN clusters; stable ids across runs (integration test). |
| 4 | Industrial relationships are calculated | ✅ | 217 industrial-associated clusters; inside-footprint / adjacent / nearby distances shown per event. |
| 5 | Persistence is calculated | ✅ | 102 persistent sources (e.g. Bhushan Power & Steel, 8 of 8 days). |
| 6 | Classification operates | ✅ | All 8 classes in use: agricultural 363, unclassified 269, vegetation 172, industrial-associated 88, mining 72, persistent industrial 36, persistent unattributed 35, gas-flare-like 17 (Reliance Jamnagar, Vadinar, Mumbai High offshore). |
| 7 | Alerts are generated only from real evidence | ✅ | 117 alerts, each with the fired rules and measured values, e.g. critical "Industrial-associated thermal event near JSW Steel Plant" (industrial proximity + unusual activity). Stale fixture incidents correctly produce no alert (test). |
| 8 | Alerts are stored | ✅ | PostgreSQL `alerts` with alert_id, incident_id, created_at, severity, status, title, description, evidence, location, facility, source, acknowledged_at, resolved_at. Duplicate insert rejected by the database (test). |
| 9 | Real-time updates work | ✅ | `/ws/stream` and `/ws/alerts` accept the app origin and reject foreign origins (403); the UI shows **Live**, and a pipeline toast arrived during verification. |
| 10 | Notification center works | ✅ | 117 unread real alert notifications; details, investigate, mark read, "Open alert centre", browser opt-in. |
| 11 | Voice commands work for supported commands | ✅ (typed) | All six specified commands resolve on live data (e.g. "How many persistent thermal sources are active?" → 102, 64 industrial, opens the filtered page); "Order a pizza" is refused. The microphone path could not be exercised in the development browser pane (capture is blocked there); the UI shows that state honestly and offers typing. |
| 12 | Investigation page works | ✅ | `/investigation/:id`: satellite map with detections, cluster extent and facility footprint; event facts; detection history; daily activity; classification rationale and rejected alternatives; 10 factors; alert history; timeline; satellites; land cover; detections table; provenance. |
| 13 | Professional light-theme dashboard works | ✅ | All eight sections checked in the browser; layout issues found during the check were fixed (table column widths, tab scrollbar, map attribution, grid-map framing). |
| 14 | Analytics use real backend data | ✅ | Totals in the API reconcile with the daily series and the grid (integration test); empty and no-data states are explicit. |
| 15 | Tests pass | ✅ | **112 passed** (unit + PostGIS integration on a disposable `_test` database): FIRMS parsing, DB operations, clustering, distance, persistence, classification, intelligence, alert rules, duplicate prevention, voice interpreter, API endpoints. |

## Security

* Secrets only in `.env` (git-ignored; `.env.example` documents every variable without values).
* The browser bundle contains no credentials or database details (checked on the production build).
* Database, webhook and SMTP credentials stay server-side; `/api/notifications/channels` reports
  configuration state only.
* CORS and WebSocket origins are allow-listed (`CORS_ORIGINS`); inputs are validated by FastAPI /
  pydantic (lengths, enums, ranges).
* Security headers on every response; pipeline trigger protected by `ADMIN_API_TOKEN` in production.

## Fixes made during verification

* Voice: "what can you do" was stripped as politeness before matching (caught by a new test).
* WebSocket 403 for the production-preview origin: added the local preview origin to `CORS_ORIGINS`.
* A dev reload stalled behind open streaming connections: graceful shutdown is now bounded
  (`--timeout-graceful-shutdown`, also in the backend Dockerfile).
* nginx now proxies `/ws/` with the WebSocket upgrade (Stage 3 deployment prep).

## Known limitations

* Classification is inferred from satellite heat plus open data; OSM coverage is uneven and
  nothing is ground-verified.
* Persistence is bounded by stored history (FIRMS keyless feed: 7 days at first; ~9 days held now).
* Analysis on Neon takes about 4 minutes per run, dominated by the ~210 ms network round trip
  from the development machine; a server co-located with Neon will be faster.
* E-mail and webhook delivery are implemented but not configured, so they are reported as
  "not configured" rather than exercised.
