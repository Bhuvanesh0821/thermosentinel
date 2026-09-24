# Intelligence methodology (engine `ts-intel-2.0`, classifier `ts-rules 2.0`)

The engine combines independent lines of **real** evidence into a classification, an evidence
strength, a 0-100 risk score and a priority. It is deliberately rule-based and transparent:
no labelled ground truth exists yet, so every output must be auditable factor by factor.
**No trained model is used or claimed**; the API reports `classifier.kind = "rule-based baseline"`
and `trained_model: false`.
Sources: `backend/app/analytics/{features,intelligence,classifier}.py`, `backend/app/alerts/rules.py`
(unit-tested in `tests/test_intelligence.py` and `tests/test_alert_rules.py`).

## 1. Clustering (what is an "event")

ST-DBSCAN over the last `CLUSTER_WINDOW_DAYS` (10): two detections are neighbours when they are
within `CLUSTER_EPS_KM` (1.5 km, about 4 VIIRS pixels) **and** `CLUSTER_MAX_GAP_HOURS` (72 h)
of each other. With `min_samples=1`, an isolated detection is its own (single-observation)
cluster, so no real detection is dropped. Cluster ids are kept stable across runs by
matching new clusters to the previous cluster that contributed most of their detections.

## 2. Evidence

| Evidence | How it is measured |
|----------|--------------------|
| Thermal intensity | Max FRP (MW) of member detections |
| Observation count | Number of detections in the cluster |
| Persistence | Distinct UTC days with a detection within 1 km over the last 30 days, **divided by the days of FIRMS data actually held** |
| Industrial proximity | PostGIS distance from cluster centre to the nearest active facility's **outline** (or point); relationship `inside_footprint` / `adjacent` ≤1 km / `nearby` ≤3 km / `distant` ≤10 km / `none` |
| Facility relevance | Plausibility that the facility type emits observable heat (flare, refinery, steel = 1.0 … generic works = 0.4) |
| Member share | Fraction of the cluster's detections within 3 km of that facility (guards against large agricultural clusters) |
| Land cover | ESA WorldCover class fractions within 250 m (built-up/bare vs cropland vs vegetation) |
| Detection confidence | FIRMS confidence (VIIRS low/nominal/high → 0.3/0.6/0.9; MODIS % / 100) |
| Night share | Fraction of night-time detections (flares/furnaces burn at night; most crop fires by day) |

## 3. Persistence categories

| Category | Rule |
|----------|------|
| persistent | ≥ 5 detection days **and** ≥ 5 days of coverage **and** ratio ≥ 25 % |
| recurring | ≥ 2 detection days (not persistent) |
| insufficient_history | 1 detection day and < 5 days of coverage - recurrence cannot be judged |
| transient | 1 detection day with adequate coverage |

A location is never called persistent without enough stored history.

## 4. Intelligence score (0-100)

`intelligence_score = 100 × Σ(wᵢ·sᵢ) / Σ(wᵢ over available factors)` (also returned as `risk_score`).

| Factor (`key`) | Weight | Normalised score sᵢ |
|----------------|-------:|---------------------|
| Proximity to industrial facility (`industrial_proximity`) | 0.18 | inside outline 1.0 · ≤1 km 0.85 · ≤3 km 0.55 · ≤10 km 0.15 · none 0 |
| Temporal persistence (`temporal_persistence`) | 0.16 | persistent 1.0 · recurring 0.6 · insufficient history 0.3 · transient 0.15 |
| Fire radiative power (`frp`) | 0.15 | log10(1+max FRP) / log10(301), capped at 1 |
| Thermal intensity (`thermal_intensity`) | 0.08 | peak brightness temperature scaled 300-400 K |
| Observation frequency (`observation_frequency`) | 0.08 | ln(1+f)/ln(11); f = detections within the persistence radius per day of FIRMS coverage |
| Industrial facility type (`facility_type`) | 0.08 | thermal relevance of the facility type (flare/refinery/steel 1.0 … generic works 0.4) |
| Satellite detection confidence (`satellite_confidence`) | 0.08 | mean FIRMS confidence |
| Spatial concentration (`spatial_concentration`) | 0.08 | 1 / (1 + extent_km / 0.75) for multi-detection events; compact heat (stacks, flares) scores high |
| Land-cover context (`land_cover_context`) | 0.07 | min(1, 1.25 × built-up + bare share) |
| Night-time detections (`night_detection`) | 0.04 | night share |

Missing evidence (e.g. land cover not yet sampled, a single detection for concentration) is
**excluded and the remaining weights are renormalised** - absence of data neither raises nor
lowers the score, and is listed as a caveat. Every factor is returned with its measured value,
normalised score, weight, contribution and a note (`GET /api/clusters/{id}/intelligence`).

`risk_level`: **critical** ≥ 80 *and* inside/adjacent to a facility · **high** ≥ 60 · **medium** ≥ 40 · **low** < 40.

## 5. Classification framework (hedged labels)

`Classifier` is an interface (`name`, `version`, `kind`, `trained`, `classify(features)`). Today
the only registered implementation is the transparent `RuleBasedClassifier`, selected with
`CLASSIFIER=rules`. A trained model can later be registered behind the same interface without
changing the pipeline, API or UI; `ml/export_features.py` exports the same feature rows for
labelling.

Rules are evaluated in order; the first satisfied class wins, and the closest alternatives that
were **not** satisfied are returned with the reason (`alternatives_rejected`).

| # | Class (`key`) | Conditions |
|---|---------------|------------|
| 1 | Gas-flare-like activity (`gas_flare_like`) | hydrocarbon site (flare, refinery, oil & gas, LNG, petrochemical) within 3 km **or** offshore with no other facility nearby; recurring; ≥ 30 % night detections; compact (≤ 1.5 km) |
| 2 | Mining-associated thermal activity (`mining_associated`) | mapped mining area within 3 km |
| 3 | Persistent industrial thermal source (`persistent_industrial_source`) | facility with thermal relevance ≥ 0.6 within 3 km and persistent heat |
| 4 | Industrial-associated thermal event (`industrial_associated_event`) | facility with relevance ≥ 0.4 within 3 km, unless it is a transient fire merely *near* a site in ≥ 60 % cropland |
| 5 | Persistent thermal source, no mapped facility (`persistent_unattributed_source`) | persistent heat, no facility within 3 km |
| 6 | Possible agricultural burning (`agricultural_burning`) | ≥ 50 % cropland, not persistent, no stronger industrial evidence |
| 7 | Possible wildfire / vegetation fire (`vegetation_fire`) | ≥ 50 % tree/shrub/grass/wetland, not persistent, no facility |
| 8 | Unclassified thermal anomaly (`unclassified_anomaly`) | otherwise (including when land cover is unavailable) |

Hypotheses (e.g. "pattern consistent with gas flaring") are shown separately and marked as
hypotheses. Every assessment carries the caveat that it is inferred from satellite and open
geospatial data and is not a confirmed ground observation. The word "confirmed" is never used.

**Evidence strength** (low/medium/high) counts converging, independent evidence lines (strong
association, recurrence, built-up land or offshore, night-time heat, ≥ 3 detections) and subtracts
contradicting ones (cropland/vegetation surroundings, low member share).

## 6. Incidents and the alert engine

An active cluster becomes an **incident** when its class is one of classes 1-5 and its score
≥ `INCIDENT_MIN_SCORE` (40). Status follows the latest detection: active (< 24 h), monitoring
(< 72 h), closed.

Each open incident is evaluated against configurable rules (`GET /api/alerts/rules`):

| Rule (`key`) | Fires when | Effect |
|--------------|-----------|--------|
| High thermal intensity (`high_intensity`) | max FRP in the last 24 h ≥ `ALERT_RULE_HIGH_FRP_MW` (50) | raises severity one level |
| Repeated observations (`repeated_observations`) | ≥ `ALERT_RULE_REPEAT_MIN_24H` (5) detections in 24 h | evidence |
| Persistent activity (`persistent_activity`) | location classified persistent | evidence |
| Industrial proximity (`industrial_proximity`) | inside / ≤ 1 km of a facility with relevance ≥ 0.6 | evidence |
| Unusual temporal behaviour (`unusual_activity`) | 24 h detections ≥ `ALERT_RULE_SPIKE_FACTOR` (3) × the location's own daily baseline, and ≥ 4 | raises severity one level |
| High-confidence detection (`high_confidence`) | high-confidence detection with FRP ≥ 10 MW in 24 h | evidence |

Severity = incident priority, raised one level by an escalating rule; **critical requires an
inside/adjacent facility link**. Alerts below `ALERT_MIN_PRIORITY` (medium) are not raised.
Every fired rule is stored with its measured value and threshold.

**No duplicates:** one alert per incident while it is unresolved - enforced in code *and* by a
partial unique index (`uq_alert_open_per_incident`). Later rule hits update the alert; a higher
severity escalates it (`escalation_count`); it is auto-resolved when the incident closes.
Notifications are keyed by `(alert, channel, recipient, event)`, so each `created` /
`escalated:<severity>` event is delivered once per channel: in-app (always), browser
(client-side, with permission), webhook (`NOTIFY_WEBHOOK_URL`) and e-mail (`SMTP_*`,
`NOTIFY_EMAIL_TO`). Credentials stay server-side. Events stream live over `/ws/alerts`,
`/ws/stream` and SSE `/api/stream`.

## 7. Known limitations

* OSM facility coverage in India is uneven; "no facility nearby" can mean "not mapped".
* FIRMS cannot distinguish causes; classification is contextual inference.
* Persistence is bounded by the stored history (the keyless feed provides 7 days at first).
* Natural Earth 1:10m boundary accuracy is about 1 km near international borders.
