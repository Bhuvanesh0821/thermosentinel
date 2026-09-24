-- 0002: Core ThermoSentinel schema.
--
-- Conventions
--   * All points are stored twice: plain latitude/longitude (double precision, exact values
--     as delivered by the source) and a PostGIS geography(Point, 4326) column used for
--     spatial indexing and metre-based distance queries.
--   * Every externally sourced row carries source_id (data_sources.id) and a source-native
--     identifier so provenance is always traceable.
--   * Timestamps are timestamptz (UTC).

-- ---------------------------------------------------------------------------------
-- Data source registry + runtime status
-- ---------------------------------------------------------------------------------
CREATE TABLE data_sources (
    id                text PRIMARY KEY,
    name              text NOT NULL,
    category          text NOT NULL CHECK (category IN ('thermal', 'infrastructure', 'land_cover', 'imagery', 'boundary')),
    provider          text NOT NULL,
    url               text,
    license           text,
    description       text,
    enabled           boolean NOT NULL DEFAULT true,
    status            text NOT NULL DEFAULT 'unknown'
                      CHECK (status IN ('unknown', 'connected', 'degraded', 'unavailable', 'not_configured', 'disabled')),
    status_message    text,
    last_attempt_at   timestamptz,
    last_success_at   timestamptz,
    last_error_at     timestamptz,
    last_error        text,
    last_record_count integer,
    config            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_data_sources_updated BEFORE UPDATE ON data_sources
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------------
-- Ingestion / analysis run log (provenance of every write)
-- ---------------------------------------------------------------------------------
CREATE TABLE ingestion_runs (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id         text REFERENCES data_sources(id),
    job               text NOT NULL,
    status            text NOT NULL DEFAULT 'running'
                      CHECK (status IN ('running', 'success', 'partial', 'failed')),
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz,
    records_fetched   integer NOT NULL DEFAULT 0,
    records_valid     integer NOT NULL DEFAULT 0,
    records_inserted  integer NOT NULL DEFAULT 0,
    records_updated   integer NOT NULL DEFAULT 0,
    records_rejected  integer NOT NULL DEFAULT 0,
    params            jsonb NOT NULL DEFAULT '{}'::jsonb,
    details           jsonb NOT NULL DEFAULT '{}'::jsonb,
    error             text
);
CREATE INDEX ix_ingestion_runs_job_started ON ingestion_runs (job, started_at DESC);
CREATE INDEX ix_ingestion_runs_source_started ON ingestion_runs (source_id, started_at DESC);

-- ---------------------------------------------------------------------------------
-- Industrial facilities (OpenStreetMap via Overpass)
-- ---------------------------------------------------------------------------------
CREATE TABLE industrial_facilities (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id          text NOT NULL REFERENCES data_sources(id),
    source_ref         text NOT NULL,              -- e.g. 'way/91585872'
    name               text,
    facility_type      text NOT NULL,
    facility_subtype   text,
    operator           text,
    website            text,
    latitude           double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude          double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    geom               geography(Point, 4326) NOT NULL,
    footprint          geography(Geometry, 4326),  -- mapped site outline where available
    footprint_area_m2  double precision,
    tags               jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_timestamp   timestamptz,                -- OSM database snapshot time
    ingestion_run_id   bigint REFERENCES ingestion_runs(id) ON DELETE SET NULL,
    is_active          boolean NOT NULL DEFAULT true,
    first_seen_at      timestamptz NOT NULL DEFAULT now(),
    last_seen_at       timestamptz NOT NULL DEFAULT now(),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_facilities_source UNIQUE (source_id, source_ref)
);
CREATE INDEX ix_facilities_geom ON industrial_facilities USING GIST (geom);
CREATE INDEX ix_facilities_footprint ON industrial_facilities USING GIST (footprint);
CREATE INDEX ix_facilities_type ON industrial_facilities (facility_type) WHERE is_active;
CREATE TRIGGER trg_facilities_updated BEFORE UPDATE ON industrial_facilities
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------------
-- Land cover samples (ESA WorldCover) around thermal locations
-- ---------------------------------------------------------------------------------
CREATE TABLE land_cover (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id           text NOT NULL REFERENCES data_sources(id),
    dataset_version     text NOT NULL,
    cell_key            text NOT NULL,             -- deduplication key (rounded location + radius)
    latitude            double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude           double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    geom                geography(Point, 4326) NOT NULL,
    sample_radius_m     integer NOT NULL,
    resolution_m        double precision,
    status              text NOT NULL CHECK (status IN ('ok', 'no_data', 'error')),
    dominant_class_code smallint,
    dominant_class_name text,
    dominant_fraction   real,
    class_fractions     jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_tile         text,
    error               text,
    sampled_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_land_cover_cell UNIQUE (source_id, dataset_version, cell_key)
);
CREATE INDEX ix_land_cover_geom ON land_cover USING GIST (geom);

-- ---------------------------------------------------------------------------------
-- Thermal clusters (spatio-temporal events derived from observations)
-- BY DEFAULT identity: the clustering engine pre-allocates ids for bulk upserts.
-- ---------------------------------------------------------------------------------
CREATE TABLE thermal_clusters (
    id                           bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status                       text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'merged')),
    merged_into_id               bigint REFERENCES thermal_clusters(id) ON DELETE SET NULL,
    center_latitude              double precision NOT NULL CHECK (center_latitude BETWEEN -90 AND 90),
    center_longitude             double precision NOT NULL CHECK (center_longitude BETWEEN -180 AND 180),
    geom                         geography(Point, 4326) NOT NULL,
    hull                         geography(Geometry, 4326),
    extent_radius_m              double precision,
    observation_count            integer NOT NULL CHECK (observation_count >= 0),
    max_frp                      double precision,
    avg_frp                      double precision,
    total_frp                    double precision,
    max_brightness               double precision,
    start_time                   timestamptz NOT NULL,
    end_time                     timestamptz NOT NULL,
    duration_hours               double precision,
    detection_days               integer,
    night_fraction               real,
    mean_confidence              real,
    instruments                  text[] NOT NULL DEFAULT '{}',
    products                     text[] NOT NULL DEFAULT '{}',
    -- persistence
    persistence_category         text CHECK (persistence_category IN ('transient', 'recurring', 'persistent', 'insufficient_history')),
    persistence_detection_days   integer,
    persistence_coverage_days    integer,
    persistence_ratio            real,
    persistence_details          jsonb,
    -- industrial proximity
    nearest_facility_id          bigint REFERENCES industrial_facilities(id) ON DELETE SET NULL,
    nearest_facility_distance_m  double precision,
    spatial_relationship         text CHECK (spatial_relationship IN ('inside_footprint', 'adjacent', 'nearby', 'distant', 'none')),
    industrial_association       boolean NOT NULL DEFAULT false,
    facility_member_share        real,
    -- land cover
    land_cover_id                bigint REFERENCES land_cover(id) ON DELETE SET NULL,
    -- intelligence
    classification               text,
    evidence_strength            text CHECK (evidence_strength IN ('low', 'medium', 'high')),
    risk_score                   real CHECK (risk_score BETWEEN 0 AND 100),
    priority                     text CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    intelligence                 jsonb,
    analysis_version             text,
    analyzed_at                  timestamptz,
    created_at                   timestamptz NOT NULL DEFAULT now(),
    updated_at                   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_cluster_time CHECK (end_time >= start_time)
);
CREATE INDEX ix_clusters_geom ON thermal_clusters USING GIST (geom);
CREATE INDEX ix_clusters_status_end ON thermal_clusters (status, end_time DESC);
CREATE INDEX ix_clusters_risk ON thermal_clusters (risk_score DESC) WHERE status = 'active';
CREATE INDEX ix_clusters_classification ON thermal_clusters (classification) WHERE status = 'active';
CREATE TRIGGER trg_clusters_updated BEFORE UPDATE ON thermal_clusters
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------------
-- Thermal observations (NASA FIRMS active fire detections)
-- ---------------------------------------------------------------------------------
CREATE TABLE thermal_observations (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id          text NOT NULL REFERENCES data_sources(id),
    source_mode        text NOT NULL CHECK (source_mode IN ('api', 'public_feed')),
    source_record_key  text NOT NULL,              -- product|date|time|lat|lon (dedupe)
    product            text NOT NULL,              -- e.g. VIIRS_SNPP_NRT
    instrument         text NOT NULL,              -- VIIRS | MODIS
    satellite          text,                       -- raw FIRMS code (N, N20, N21, T, A)
    satellite_name     text,                       -- Suomi NPP, NOAA-20, ...
    latitude           double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude          double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    geom               geography(Point, 4326) NOT NULL,
    brightness         double precision,           -- K (VIIRS I-4 / MODIS 21-22)
    brightness_2       double precision,           -- K (VIIRS I-5 / MODIS 31)
    frp                double precision CHECK (frp IS NULL OR frp >= 0),   -- MW
    scan               double precision,
    track              double precision,
    acq_date           date NOT NULL,
    acq_time           char(4) NOT NULL,           -- HHMM UTC as delivered
    acquired_at        timestamptz NOT NULL,
    confidence_raw     text,
    confidence_level   text CHECK (confidence_level IN ('low', 'nominal', 'high')),
    confidence_pct     smallint CHECK (confidence_pct IS NULL OR confidence_pct BETWEEN 0 AND 100),
    daynight           char(1) CHECK (daynight IN ('D', 'N')),
    version            text,
    cluster_id         bigint REFERENCES thermal_clusters(id) ON DELETE SET NULL,
    ingestion_run_id   bigint REFERENCES ingestion_runs(id) ON DELETE SET NULL,
    ingested_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_observation_record UNIQUE (source_record_key)
);
CREATE INDEX ix_observations_geom ON thermal_observations USING GIST (geom);
CREATE INDEX ix_observations_acquired ON thermal_observations (acquired_at DESC);
CREATE INDEX ix_observations_cluster ON thermal_observations (cluster_id);
CREATE INDEX ix_observations_product_acquired ON thermal_observations (product, acquired_at DESC);

-- ---------------------------------------------------------------------------------
-- Cluster <-> facility spatial relationships (top-k nearest within search radius)
-- ---------------------------------------------------------------------------------
CREATE TABLE cluster_facility_proximity (
    cluster_id    bigint NOT NULL REFERENCES thermal_clusters(id) ON DELETE CASCADE,
    facility_id   bigint NOT NULL REFERENCES industrial_facilities(id) ON DELETE CASCADE,
    rank          smallint NOT NULL,
    distance_m    double precision NOT NULL,
    relationship  text NOT NULL CHECK (relationship IN ('inside_footprint', 'adjacent', 'nearby', 'distant')),
    computed_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (cluster_id, facility_id)
);
CREATE INDEX ix_proximity_facility ON cluster_facility_proximity (facility_id);

-- ---------------------------------------------------------------------------------
-- Incidents (clusters that meet the incident criteria of the intelligence engine)
-- ---------------------------------------------------------------------------------
CREATE TABLE incidents (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id          bigint NOT NULL REFERENCES thermal_clusters(id) ON DELETE CASCADE,
    facility_id         bigint REFERENCES industrial_facilities(id) ON DELETE SET NULL,
    title               text NOT NULL,
    classification      text NOT NULL,
    priority            text NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    risk_score          real NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    status              text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'monitoring', 'closed')),
    latitude            double precision NOT NULL,
    longitude           double precision NOT NULL,
    geom                geography(Point, 4326) NOT NULL,
    first_detected_at   timestamptz NOT NULL,
    last_detected_at    timestamptz NOT NULL,
    observation_count   integer NOT NULL,
    max_frp             double precision,
    summary             text,
    evidence            jsonb NOT NULL DEFAULT '{}'::jsonb,
    acknowledged_at     timestamptz,
    closed_at           timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_incident_cluster UNIQUE (cluster_id)
);
CREATE INDEX ix_incidents_geom ON incidents USING GIST (geom);
CREATE INDEX ix_incidents_status_priority ON incidents (status, priority);
CREATE INDEX ix_incidents_last_detected ON incidents (last_detected_at DESC);
CREATE TRIGGER trg_incidents_updated BEFORE UPDATE ON incidents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------------
-- Alerts (generated on new incidents / escalations)
-- ---------------------------------------------------------------------------------
CREATE TABLE alerts (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    incident_id      bigint REFERENCES incidents(id) ON DELETE CASCADE,
    cluster_id       bigint REFERENCES thermal_clusters(id) ON DELETE SET NULL,
    alert_type       text NOT NULL CHECK (alert_type IN ('new_incident', 'priority_escalation', 'renewed_activity')),
    severity         text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    title            text NOT NULL,
    message          text NOT NULL,
    status           text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'resolved')),
    dedupe_key       text NOT NULL,
    evidence         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    acknowledged_at  timestamptz,
    resolved_at      timestamptz,
    CONSTRAINT uq_alert_dedupe UNIQUE (dedupe_key)
);
CREATE INDEX ix_alerts_status_created ON alerts (status, created_at DESC);
CREATE INDEX ix_alerts_incident ON alerts (incident_id);

-- ---------------------------------------------------------------------------------
-- Notifications (per-channel delivery records for alerts)
-- ---------------------------------------------------------------------------------
CREATE TABLE notifications (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_id     bigint REFERENCES alerts(id) ON DELETE CASCADE,
    channel      text NOT NULL CHECK (channel IN ('in_app', 'webhook', 'email', 'sms', 'voice')),
    recipient    text NOT NULL DEFAULT '',
    title        text NOT NULL,
    body         text NOT NULL,
    status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed', 'read')),
    attempts     integer NOT NULL DEFAULT 0,
    last_error   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    sent_at      timestamptz,
    read_at      timestamptz,
    CONSTRAINT uq_notification_delivery UNIQUE (alert_id, channel, recipient)
);
CREATE INDEX ix_notifications_channel_status ON notifications (channel, status, created_at DESC);

-- ---------------------------------------------------------------------------------
-- System events (audit trail; also streamed to the UI)
-- ---------------------------------------------------------------------------------
CREATE TABLE system_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type  text NOT NULL,
    severity    text NOT NULL DEFAULT 'info' CHECK (severity IN ('debug', 'info', 'warning', 'error')),
    source      text,
    message     text NOT NULL,
    details     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_system_events_created ON system_events (created_at DESC);
CREATE INDEX ix_system_events_type ON system_events (event_type, created_at DESC);

-- ---------------------------------------------------------------------------------
-- Job leases (prevents overlapping pipeline runs across processes; pooler-safe)
-- ---------------------------------------------------------------------------------
CREATE TABLE job_locks (
    name          text PRIMARY KEY,
    holder        text NOT NULL,
    acquired_at   timestamptz NOT NULL DEFAULT now(),
    locked_until  timestamptz NOT NULL
);
