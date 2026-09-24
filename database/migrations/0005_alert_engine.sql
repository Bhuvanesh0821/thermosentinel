-- 0005: Stage 2 rule-based alert engine and multi-channel notifications.
--
-- One alert per underlying event (incident): rules that fire later update the same alert
-- (and escalate it) instead of creating duplicates. Alerts produced by the Stage 1 engine are
-- derived data; they are removed here and regenerated from the same stored evidence by the new
-- engine on the next analysis run.

DELETE FROM notifications;
DELETE FROM alerts;

ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_alert_type_check;
ALTER TABLE alerts DROP CONSTRAINT IF EXISTS uq_alert_dedupe;
ALTER TABLE alerts DROP COLUMN IF EXISTS dedupe_key;
ALTER TABLE alerts RENAME COLUMN message TO description;

ALTER TABLE alerts
    ADD COLUMN facility_id        bigint REFERENCES industrial_facilities(id) ON DELETE SET NULL,
    ADD COLUMN latitude           double precision,
    ADD COLUMN longitude          double precision,
    ADD COLUMN geom               geography(Point, 4326),
    ADD COLUMN source             text NOT NULL DEFAULT 'ThermoSentinel alert engine (NASA FIRMS evidence)',
    ADD COLUMN rules              text[] NOT NULL DEFAULT '{}',
    ADD COLUMN escalation_count   integer NOT NULL DEFAULT 0,
    ADD COLUMN last_triggered_at  timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN resolution         text,
    ADD COLUMN updated_at         timestamptz NOT NULL DEFAULT now();

ALTER TABLE alerts ADD CONSTRAINT alerts_alert_type_check CHECK (alert_type IN ('event'));
ALTER TABLE alerts ALTER COLUMN alert_type SET DEFAULT 'event';

-- Duplicate prevention: at most one unresolved alert per incident.
CREATE UNIQUE INDEX uq_alert_open_per_incident ON alerts (incident_id) WHERE status <> 'resolved';
CREATE INDEX ix_alerts_geom ON alerts USING GIST (geom);
CREATE INDEX ix_alerts_severity ON alerts (severity, created_at DESC);
CREATE TRIGGER trg_alerts_updated BEFORE UPDATE ON alerts FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Notifications: one delivery per (alert, channel, recipient, alert event) so an escalation
-- can notify again, but the same event is never delivered twice.
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS uq_notification_delivery;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_channel_check;
ALTER TABLE notifications ADD CONSTRAINT notifications_channel_check
    CHECK (channel IN ('in_app', 'browser', 'webhook', 'email'));
ALTER TABLE notifications ADD COLUMN event text NOT NULL DEFAULT 'created';
ALTER TABLE notifications ADD COLUMN severity text;
ALTER TABLE notifications ADD CONSTRAINT uq_notification_event UNIQUE (alert_id, channel, recipient, event);
