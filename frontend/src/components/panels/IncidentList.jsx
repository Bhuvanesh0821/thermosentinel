import { Siren } from 'lucide-react';
import { useApi } from '../../hooks/useApi.js';
import { filterParams, useApp } from '../../state/AppContext.jsx';
import { PRIORITY } from '../../utils/constants.js';
import { fmtInt, fmtNum, fmtRelative, fmtUtc, titleCase } from '../../utils/format.js';
import { PriorityBadge } from '../common/Badges.jsx';
import { Badge, EmptyState, ErrorState, SkeletonRows } from '../common/ui.jsx';
import s from './lists.module.css';

export default function IncidentList() {
  const { filters, mapBounds, setSelection, focusMap } = useApp();
  const { data, meta, error, loading, reload } = useApi('/api/incidents', {
    status: 'active,monitoring',
    limit: 100,
    ...filterParams(filters, mapBounds),
    confidence: undefined,
  });

  return (
    <div className={s.list}>
      <div className={s.toolbar}>
        <span className={s.total}>{meta ? `${fmtInt(meta.total)} open · by priority` : ''}</span>
      </div>
      {loading && (
        <div className={s.pad}>
          <SkeletonRows rows={5} height={64} />
        </div>
      )}
      {error && <ErrorState error={error} onRetry={reload} />}
      {!loading && !error && data?.length === 0 && (
        <EmptyState icon={Siren} title="No open incidents">
          Incidents are opened automatically when a cluster is classified as an industrial or persistent thermal source and its
          risk score passes the configured threshold.
        </EmptyState>
      )}
      <ul className={s.items}>
        {data?.map((inc) => (
          <li key={inc.id}>
            <button
              type="button"
              className={s.item}
              style={{ '--bar': PRIORITY[inc.priority]?.color }}
              onClick={() => {
                setSelection({ type: 'cluster', id: inc.cluster_id, incidentId: inc.id });
                focusMap(inc.longitude, inc.latitude, 11);
              }}
            >
              <div className={s.itemTop}>
                <span className={`${s.ref} mono`}>{inc.reference}</span>
                <PriorityBadge priority={inc.priority} />
                <Badge tone={inc.status === 'active' ? 'err' : 'warn'} variant="outline">
                  {titleCase(inc.status)}
                </Badge>
                <span className={s.score} title="Risk score (0–100)">
                  <span className="mono">{fmtNum(inc.risk_score, 0)}</span>
                </span>
              </div>
              <div className={s.itemTitle}>{inc.title}</div>
              <div className={s.itemMeta}>
                <span>{inc.classification_label}</span>
                <span>
                  <span className="mono">{fmtInt(inc.observation_count)}</span> det
                </span>
                <span className={s.time} title={`Last detection ${fmtUtc(inc.last_detected_at)}`}>
                  {fmtRelative(inc.last_detected_at)}
                </span>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
