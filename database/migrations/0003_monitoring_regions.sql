-- 0003: Monitoring region (India official-claim boundary + EEZ).
-- Loaded by the API from database/boundaries/india_monitoring_area.geojson; every stored
-- observation and facility must lie inside the 'monitoring_area' polygon.
CREATE TABLE monitoring_regions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL,
    role        text NOT NULL CHECK (role IN ('land', 'monitoring_area')),
    geom        geography(MultiPolygon, 4326) NOT NULL,
    properties  jsonb NOT NULL DEFAULT '{}'::jsonb,
    checksum    text NOT NULL,
    loaded_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_monitoring_region_role UNIQUE (name, role)
);
CREATE INDEX ix_monitoring_regions_geom ON monitoring_regions USING GIST (geom);
