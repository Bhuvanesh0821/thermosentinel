import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileSearch, Flame, MapPin } from 'lucide-react';
import FilterBar from '../components/common/FilterBar.jsx';
import { ClassificationTag, PersistenceBadge, PriorityBadge } from '../components/common/Badges.jsx';
import { Button, EmptyState, ErrorState, Meter, Segmented, Select, SkeletonRows } from '../components/common/ui.jsx';
import { useApi } from '../hooks/useApi.js';
import { useQueryFilters } from '../hooks/useQueryFilters.js';
import { filterParams, useApp } from '../state/AppContext.jsx';
import { PRIORITY } from '../utils/constants.js';
import { fmtCoord, fmtDistance, fmtInt, fmtNum, fmtPct, fmtRelative, fmtUtc } from '../utils/format.js';
import s from './page.module.css';

const STATUS = [
  { value: 'active', label: 'Active' },
  { value: 'all', label: 'All' },
];
const SORTS = [
  { value: 'risk', label: 'Sort: intelligence score' },
  { value: 'recent', label: 'Sort: most recent' },
  { value: 'frp', label: 'Sort: peak FRP' },
  { value: 'count', label: 'Sort: detections' },
];
const PAGE = 50;

/**
 * Persistent and recurring thermal sources: clusters whose location was re-detected on multiple
 * distinct days within the persistence look-back window.
 */
export default function ThermalSourcesView() {
  useQueryFilters();
  const navigate = useNavigate();
  const { filters, mapBounds, setSelection, focusMap } = useApp();
  const [status, setStatus] = useState('active');
  const [sort, setSort] = useState('risk');
  const [offset, setOffset] = useState(0);
  const base = filterParams(filters, mapBounds);
  const params = {
    status,
    ...base,
    persistence: base.persistence || 'persistent,recurring',
    sort,
    limit: PAGE,
    offset,
  };
  useEffect(() => setOffset(0), [status, sort, filters, mapBounds]);
  const { data, meta, error, loading, refreshing, reload } = useApi('/api/clusters', params);

  function showOnMap(c) {
    setSelection({ type: 'cluster', id: c.id, incidentId: c.incident_id });
    focusMap(c.center_longitude, c.center_latitude, 11);
    navigate('/dashboard');
  }

  return (
    <div className={s.page}>
      <div className={s.header}>
        <div>
          <h1 className={s.title}>Thermal sources</h1>
          <p className={s.subtitle}>
            Locations re-detected by satellite on several distinct days - persistent (most days observed) or recurring. Persistent sources
            near industrial infrastructure are the strongest indicators of continuous industrial heat such as flaring or furnaces.
          </p>
        </div>
      </div>
      <div className={s.stack}>
        <FilterBar fields={['severity', 'event', 'facility', 'persistence', 'confidence', 'area']} />
        <div className={`${s.card} ${s.tableCard}`} data-refreshing={refreshing}>
          <div className={s.tableToolbar}>
            <Segmented options={STATUS} value={status} onChange={setStatus} label="Cluster status" />
            <Select label="Sort order" value={sort} onChange={(v) => setSort(v || 'risk')} options={SORTS} />
            {meta && <span className={s.muted}>{fmtInt(meta.total)} sources</span>}
          </div>
          {loading && (
            <div style={{ padding: 12 }}>
              <SkeletonRows rows={8} height={36} />
            </div>
          )}
          {error && <ErrorState error={error} onRetry={reload} />}
          {!loading && !error && data?.length === 0 && (
            <EmptyState icon={Flame} title="No persistent or recurring sources match">
              A source becomes persistent once the same location is detected on several distinct days. Widen the filters or wait for more
              satellite passes.
            </EmptyState>
          )}
          {data?.length > 0 && (
            <table className={s.table}>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Persistence</th>
                  <th>Classification</th>
                  <th>Nearest facility</th>
                  <th className={s.num}>Detections</th>
                  <th className={s.num}>Peak FRP</th>
                  <th className={s.num}>Night</th>
                  <th className={s.num}>Score</th>
                  <th>Last seen</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((c) => (
                  <tr key={c.id} onClick={() => (c.incident_id ? navigate(`/investigation/${c.incident_id}`) : showOnMap(c))}>
                    <td style={{ boxShadow: c.priority ? `inset 3px 0 0 ${PRIORITY[c.priority]?.color}` : undefined }}>
                      <div className={s.strong}>Cluster #{c.id}</div>
                      <div className={`mono ${s.muted} ${s.nowrap}`}>{fmtCoord(c.center_latitude, c.center_longitude, 3)}</div>
                    </td>
                    <td>
                      <PersistenceBadge category={c.persistence_category} />
                      <div className={s.muted}>
                        {c.persistence_detection_days ?? '—'} of {c.persistence_coverage_days ?? '—'} days
                      </div>
                      {c.persistence_coverage_days > 0 && (
                        <div style={{ width: 110, marginTop: 4 }}>
                          <Meter
                            value={c.persistence_detection_days || 0}
                            max={c.persistence_coverage_days}
                            color="#2a78d6"
                            title={`Detected on ${c.persistence_detection_days} of ${c.persistence_coverage_days} days of FIRMS coverage`}
                          />
                        </div>
                      )}
                    </td>
                    <td>
                      <ClassificationTag classification={c.classification} short />
                    </td>
                    <td>
                      {c.facility_name || c.nearest_facility_id ? (
                        <>
                          <div>{c.facility_name || 'Unnamed facility'}</div>
                          <div className={s.muted}>{fmtDistance(c.nearest_facility_distance_m)}</div>
                        </>
                      ) : (
                        <span className={s.muted}>None within search radius</span>
                      )}
                    </td>
                    <td className={`${s.num} mono`}>{fmtInt(c.observation_count)}</td>
                    <td className={`${s.num} mono`}>{c.max_frp != null ? `${fmtNum(c.max_frp)} MW` : '—'}</td>
                    <td className={`${s.num} mono`}>{c.night_fraction != null ? fmtPct(c.night_fraction) : '—'}</td>
                    <td className={s.num}>
                      <span className="mono" style={{ marginRight: 6 }}>
                        {c.risk_score != null ? Math.round(c.risk_score) : '—'}
                      </span>
                      {c.priority && <PriorityBadge priority={c.priority} />}
                    </td>
                    <td className={s.nowrap} title={fmtUtc(c.end_time)}>
                      {fmtRelative(c.end_time)}
                    </td>
                    <td className={s.nowrap} onClick={(e) => e.stopPropagation()}>
                      <span style={{ display: 'inline-flex', gap: 4 }}>
                        {c.incident_id && (
                          <Button size="sm" variant="ghost" icon={FileSearch} onClick={() => navigate(`/investigation/${c.incident_id}`)}>
                            Investigate
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" icon={MapPin} onClick={() => showOnMap(c)}>
                          Map
                        </Button>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {meta && meta.total > PAGE && (
            <div className={s.pager}>
              <span>
                {fmtInt(offset + 1)}–{fmtInt(Math.min(offset + PAGE, meta.total))} of {fmtInt(meta.total)}
              </span>
              <span style={{ display: 'flex', gap: 6 }}>
                <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                  Previous
                </Button>
                <Button size="sm" disabled={offset + PAGE >= meta.total} onClick={() => setOffset(offset + PAGE)}>
                  Next
                </Button>
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
