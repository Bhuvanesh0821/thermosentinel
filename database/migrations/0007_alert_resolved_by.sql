-- Record who resolved an alert, so an operator's decision is respected: the alert engine does not
-- re-raise an alert for the same incident for 7 days after an operator resolved it, unless the
-- evidence escalates to a higher severity.

ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_by text
    CHECK (resolved_by IN ('operator', 'system'));

UPDATE alerts
   SET resolved_by = CASE WHEN resolution LIKE 'Auto-resolved%' THEN 'system' ELSE 'operator' END
 WHERE status = 'resolved' AND resolved_by IS NULL;

CREATE INDEX IF NOT EXISTS ix_alerts_operator_resolved
    ON alerts (incident_id, resolved_at DESC) WHERE resolved_by = 'operator';
