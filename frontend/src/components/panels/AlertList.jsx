import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BellRing, Check } from 'lucide-react';
import { api } from '../../api/client.js';
import { useApi } from '../../hooks/useApi.js';
import { useApp } from '../../state/AppContext.jsx';
import { PRIORITY } from '../../utils/constants.js';
import { fmtInt, fmtRelative, fmtUtc } from '../../utils/format.js';
import { PriorityBadge } from '../common/Badges.jsx';
import { Button, EmptyState, ErrorState, Segmented, SkeletonRows } from '../common/ui.jsx';
import s from './lists.module.css';

const STATUS = [
  { value: 'open', label: 'Open' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'resolved', label: 'Resolved' },
];

export const RULE_LABELS = {
  high_intensity: 'High intensity',
  repeated_observations: 'Repeated',
  persistent_activity: 'Persistent',
  industrial_proximity: 'Industrial',
  unusual_activity: 'Unusual',
  high_confidence: 'High confidence',
};

/** Compact alert list for the dashboard rail. */
export default function AlertList() {
  const navigate = useNavigate();
  const { pushToast } = useApp();
  const [status, setStatus] = useState('open');
  const [busy, setBusy] = useState(null);
  const { data, meta, error, loading, reload } = useApi('/api/alerts', { status, limit: 60 });

  async function acknowledge(alert) {
    setBusy(alert.id);
    try {
      await api.post(`/api/alerts/${alert.id}/acknowledge`);
      reload();
    } catch (e) {
      pushToast({ tone: 'error', title: 'Acknowledge failed', body: e.message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={s.list}>
      <div className={s.toolbar}>
        <Segmented options={STATUS} value={status} onChange={setStatus} label="Alert status" />
        {meta && <span className={s.total}>{fmtInt(meta.total)}</span>}
      </div>
      {loading && (
        <div className={s.pad}>
          <SkeletonRows rows={5} height={60} />
        </div>
      )}
      {error && <ErrorState error={error} onRetry={reload} />}
      {!loading && !error && data?.length === 0 && (
        <EmptyState icon={BellRing} title={`No ${status} alerts`}>
          Alerts are raised only when configured rules fire on real incident evidence.
        </EmptyState>
      )}
      <ul className={s.items}>
        {data?.map((a) => (
          <li key={a.id} className={s.alertRow} style={{ '--bar': PRIORITY[a.severity]?.color }}>
            <button
              type="button"
              className={s.alertMain}
              onClick={() => navigate(a.incident_id ? `/investigation/${a.incident_id}` : '/alerts')}
            >
              <div className={s.itemTop}>
                <PriorityBadge priority={a.severity} />
                {a.escalation_count > 0 && <span className={s.kind}>Escalated</span>}
                <span className={s.time} title={fmtUtc(a.last_triggered_at)}>
                  {fmtRelative(a.last_triggered_at)}
                </span>
              </div>
              <div className={s.itemTitle}>{a.title}</div>
              <div className={s.rules}>
                {(a.rules || []).map((r) => (
                  <span key={r} className={s.rule}>
                    {RULE_LABELS[r] || r}
                  </span>
                ))}
              </div>
            </button>
            {a.status === 'open' ? (
              <Button size="sm" icon={Check} onClick={() => acknowledge(a)} disabled={busy === a.id} className={s.ack}>
                Ack
              </Button>
            ) : (
              <span className={s.acked}>{a.status === 'resolved' ? 'Resolved' : 'Acknowledged'}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
