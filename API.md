# API reference

Interactive OpenAPI documentation: **`<API>/api/docs`** (ReDoc: `/api/redoc`, schema:
`/api/openapi.json`), where `<API>` is `http://127.0.0.1:8000` locally or the Render URL in
production (see DEPLOYMENT.md).

* All data is real (NASA FIRMS, OpenStreetMap, ESA WorldCover); nothing is synthesised.
* Browsers may call the API only from allowed origins (`FRONTEND_URL`, `CORS_ORIGINS`); the same
  list is enforced for WebSocket connections.
* State-changing operator endpoints require `X-Admin-Token` (`ADMIN_API_TOKEN`) in production.
* Heavy read endpoints (map layers, analytics) answer from an in-memory cache until the data
  changes; the `X-Cache: HIT|MISS` header shows which.

All responses use one envelope:

```json
{ "status": "ok", "data": ..., "meta": { "generated_at": "...", "total": 123, ... } }
{ "status": "error", "error": { "code": "database_not_configured", "message": "...", "details": null } }
```

Error codes include `validation_error` (422), `not_found` (404), `bad_request` (400),
`forbidden` (403), `job_busy` (409), `database_not_configured` / `database_unavailable` (503),
`upstream_error` (502), `internal_error` (500).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness + database (latency, PostGIS), FIRMS mode, scheduler, pipeline state, `environment`, `data_mode`, `pipeline_trigger`. Works without a DB. |
| GET | `/api/data-sources` | Status, provenance and licence of every source + the database. Works without a DB. |
| GET | `/api/firms` | Stored FIRMS detections (filters: `hours`, `bbox`, `product`, `instrument`, `min_frp`, `confidence`, `daynight`, paging). |
| GET | `/api/firms/{id}` | One detection. |
| GET | `/api/ingestion-runs` | Recent ingestion/analysis runs with counts and errors. |
| GET | `/api/hotspots` | Detections as GeoJSON for the map (with cluster classification). |
| GET | `/api/facilities` | Industrial facilities (`type`, `bbox`, `q`, `format=json|geojson`). |
| GET | `/api/facilities/types` | Counts per facility type. |
| GET | `/api/facilities/footprints` | Facility outlines for a bbox (GeoJSON). |
| GET | `/api/facilities/{id}` | Facility detail, OSM tags, related clusters. |
| GET | `/api/clusters` | Clusters with persistence, proximity, land cover, score (`format=json|geojson`, filters, sort). |
| GET | `/api/clusters/{id}` | Full evidence: member detections, top-3 facilities, land-cover fractions, factor breakdown. |
| GET | `/api/clusters/{id}/intelligence` | `intelligence_score`, `risk_level`, classification with rationale and rejected alternatives, factors, evidence. |
| GET | `/api/risk-zones` | Association buffers around open incidents (GeoJSON). |
| GET | `/api/incidents` | Incidents (`status`, `min_priority`, `classification`, `facility_type`, `persistence`, `bbox`, `q`, `format`). |
| GET | `/api/incidents/{id}` | Incident detail with alerts and evidence. |
| POST | `/api/incidents/{id}/acknowledge` | Acknowledge an incident. |
| GET | `/api/investigations/{incident_id}` | Investigation workspace: timeline, detections, daily/satellite summaries, facility, persistence, classification rationale, factors, alert history, provenance. |
| GET | `/api/alerts` | Alerts (`status`, `min_severity`, `rule`, `q`, `hours`, paging; `meta.by_status`). Fields: `alert_id`, `incident_id`, `severity`, `status`, `title`, `description`, `rules`, `location`, `facility`, `source`, `created_at`, `acknowledged_at`, `resolved_at`. |
| GET | `/api/alerts/{id}` | Alert detail with rule evidence (measured value vs threshold) and delivery log. |
| GET | `/api/alerts/rules` | Configured alert rules, thresholds and deduplication policy. |
| POST | `/api/alerts/{id}/acknowledge`, `/api/alerts/{id}/resolve` | Operator actions (`resolve` takes `{"note": "..."}`). |
| GET | `/api/notifications/channels` | Channel configuration and last delivery (never credentials). |
| GET | `/api/analytics/overview` | Daily detections (day/night, sensor, industrial), FRP median/p90/max, incidents by priority, persistence/classification/facility-type mixes, top persistent sources (`days`). |
| GET | `/api/analytics/grid` | Detections binned into degree cells (GeoJSON; `days`, `cell`). |
| GET | `/api/search` | Facilities, incidents, alerts and places (Nominatim, clipped to India) (`q`, `types`). |
| POST | `/api/voice/interpret` | Maps a transcript to one whitelisted action or a data-backed answer; unsupported requests return `supported: false`. |
| GET | `/api/voice/commands` | Supported voice commands. |
| GET | `/api/system/health` | API, database, FIRMS, OSM, land cover, real-time stream, notifications, scheduler: connected / degraded / unavailable; plus `failures` (last 24 h per category: ingestion, external sources, database, API, alerts, notifications, real-time; secrets redacted). |
| GET | `/api/intelligence/model` | Engine version, classifier (rule-based, not trained), classes, factor weights. |
| GET | `/api/notifications` | In-app notifications (+ unread count). |
| POST | `/api/notifications/{id}/read`, `/api/notifications/read-all` | Mark read. |
| GET | `/api/landcover` | Land-cover samples (GeoJSON). |
| GET | `/api/landcover/classes` | ESA WorldCover legend. |
| GET | `/api/map/config` | Region, basemaps, legends. |
| GET | `/api/map/boundary` | India boundary, EEZ outline and outside-mask (GeoJSON). |
| GET | `/api/stats/summary` | Dashboard aggregates for a window. |
| GET | `/api/system-events` | Audit trail of pipeline/alert events. |
| GET | `/api/stream` | Server-Sent Events: `pipeline.*`, `ingestion.*`, `analysis.*`, `alert.*`. |
| WS | `/ws/stream`, `/ws/alerts` | WebSocket streams (all events / alert events only), JSON messages, 20 s heartbeat; browser origins must be in `CORS_ORIGINS`. |
| GET | `/api/pipeline/status` | Current/last pipeline run. |
| POST | `/api/pipeline/run` | Start ingestion + analysis (requires `X-Admin-Token` when `ADMIN_API_TOKEN` is set; refused in production without one). |
| POST | `/api/demo/replay`, `/api/demo/reset` | **Development only** - exist only with `DATA_MODE=test-fixture` on a `*_test` database (404 otherwise): replay / clear the labelled FIRMS test fixture. |
| GET | `/api/voice/briefing` | Plain-language situation briefing built from live data (+ the facts used). |
