import { useState } from 'react';
import { Flame } from 'lucide-react';
import { useApi } from '../../hooks/useApi.js';
import { filterParams, useApp } from '../../state/AppContext.jsx';
import { PRIORITY, RELATIONSHIP } from '../../utils/constants.js';
import { fmtCoord, fmtDistance, fmtInt, fmtNum, fmtRelative, fmtUtc } from '../../utils/format.js';
import { ClassificationTag, PersistenceBadge } from '../common/Badges.jsx';
import { EmptyState, ErrorState, Segmented, SkeletonRows } from '../common/ui.jsx';
import s from './lists.module.css';

const SCOPES = [
  { value: 'all', label: 'All' },
  { value: 'industrial', label: 'Industrial' },
  { value: 'persistent', label: 'Persistent' },
];

export default function EventList() {
  const { filters, mapBounds, setSelection, focusMap } = useApp();
  const [scope, setScope] = useState('industrial');
  const shared = filterParams(filters, mapBounds);
  const params = {
    ...shared,
    hours: filters.hours,
    sort: 'risk',
    limit: 60,
    associated_only: scope === 'industrial' ? true : undefined,
    persistence: scope === 'persistent' ? 'persistent' : shared.persistence,
    min_observations: scope === 'all' ? 2 : undefined,
  };
  const { data, meta, error, loading, reload } = useApi('/api/clusters', params);

  return (
    <div className={s.list}>
      <div className={s.toolbar}>
        <Segmented options={SCOPES} value={scope} onChange={setScope} label="Event scope" />
        {meta && <span className={s.total}>{fmtInt(meta.total)} ranked by risk</span>}
      </div>
      {loading && (
        <div className={s.pad}>
          <SkeletonRows rows={6} height={64} />
        </div>
      )}
      {error && <ErrorState error={error} onRetry={reload} />}
      {!loading && !error && data?.length === 0 && (
        <EmptyState icon={Flame} title="No thermal events in this view">
          {scope === 'industrial'
            ? 'No active cluster matching the filters lies within 3 km of a mapped industrial facility.'
            : scope === 'persistent'
              ? 'No location matching the filters meets the persistence criteria.'
              : 'No multi-detection clusters match the current filters.'}
        </EmptyState>
      )}
      <ul className={s.items}>
        {data?.map((c) => {
          const pr = PRIORITY[c.priority];
          return (
            <li key={c.id}>
              <button
                type="button"
                className={s.item}
                style={{ '--bar': pr?.color || 'var(--border-strong)' }}
                onClick={() => {
                  setSelection({ type: 'cluster', id: c.id, incidentId: c.incident_id });
                  focusMap(c.center_longitude, c.center_latitude, 10);
                }}
              >
                <div className={s.itemTop}>
                  <ClassificationTag classification={c.classification} short />
                  <span className={s.score} title="Risk score (0–100)">
                    <span className="mono">{c.risk_score != null ? fmtNum(c.risk_score, 0) : '—'}</span>
                  </span>
                </div>
                <div className={s.itemTitle}>
                  {c.industrial_association && c.facility_name
                    ? c.facility_name
                    : c.industrial_association
                      ? `Unnamed ${c.facility_type_label?.toLowerCase() || 'facility'}`
                      : fmtCoord(c.center_latitude, c.center_longitude, 3)}
                </div>
                <div className={s.itemMeta}>
                  {c.industrial_association && (
                    <span title={RELATIONSHIP[c.spatial_relationship]}>
                      {c.facility_type_label} · {fmtDistance(c.nearest_facility_distance_m)}
                    </span>
                  )}
                  <span>
                    <span className="mono">{fmtInt(c.observation_count)}</span> det
                  </span>
                  <span>
                    <span className="mono">{fmtNum(c.max_frp)}</span> MW
                  </span>
                  <PersistenceBadge category={c.persistence_category} />
                  <span className={s.time} title={fmtUtc(c.end_time)}>
                    {fmtRelative(c.end_time)}
                  </span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
