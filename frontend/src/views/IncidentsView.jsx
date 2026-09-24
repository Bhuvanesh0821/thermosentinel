import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapPin, Search, Siren } from 'lucide-react';
import FilterBar from '../components/common/FilterBar.jsx';
import { ClassificationTag, PersistenceBadge, PriorityBadge } from '../components/common/Badges.jsx';
import { Badge, Button, EmptyState, ErrorState, Segmented, SkeletonRows } from '../components/common/ui.jsx';
import { useApi } from '../hooks/useApi.js';
import { useQueryFilters } from '../hooks/useQueryFilters.js';
import { filterParams, useApp } from '../state/AppContext.jsx';
import { PRIORITY } from '../utils/constants.js';
import { fmtDistance, fmtInt, fmtNum, fmtRelative, fmtUtc, titleCase } from '../utils/format.js';
import s from './page.module.css';

const STATUS = [
  { value: 'active,monitoring', label: 'Open' },
  { value: 'active', label: 'Active' },
  { value: 'monitoring', label: 'Monitoring' },
  { value: 'closed', label: 'Closed' },
  { value: 'active,monitoring,closed', label: 'All' },
];
const PAGE = 50;

export default function IncidentsView() {
  useQueryFilters();
  const navigate = useNavigate();
  const { filters, mapBounds, setSelection, focusMap } = useApp();
  const [status, setStatus] = useState('active,monitoring');
  const [query, setQuery] = useState('');
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setQ(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);
  const params = {
    status,
    ...filterParams(filters, mapBounds),
    confidence: undefined,
    q: q.length >= 2 ? q : undefined,
    limit: PAGE,
    offset,
  };
  useEffect(() => setOffset(0), [status, q, filters, mapBounds]);
  const { data, meta, error, loading, refreshing, reload } = useApi('/api/incidents', params);

  function showOnMap(inc) {
    setSelection({ type: 'cluster', id: inc.cluster_id, incidentId: inc.id });
    focusMap(inc.longitude, inc.latitude, 11);
    navigate('/dashboard');
  }

  return (
    <div className={s.page}>
      <div className={s.header}>
        <div>
          <h1 className={s.title}>Incidents</h1>
          <p className={s.subtitle}>
            Thermal events the intelligence engine classified as industrial or persistent, with an intelligence score above the incident
            threshold. Status follows the latest satellite detection. Select an incident to open its investigation workspace.
          </p>
        </div>
      </div>
      <div className={s.stack}>
        <FilterBar fields={['severity', 'event', 'facility', 'persistence', 'area']} />
        <div className={`${s.card} ${s.tableCard}`} data-refreshing={refreshing}>
          <div className={s.tableToolbar}>
            <Segmented options={STATUS} value={status} onChange={setStatus} label="Incident status" />
            <label className={s.searchWrap}>
              <Search size={14} />
              <input className={s.search} type="search" placeholder="Search incident titles…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search incidents" />
            </label>
            {meta && <span className={s.muted}>{fmtInt(meta.total)} incidents</span>}
          </div>
          {loading && (
            <div style={{ padding: 12 }}>
              <SkeletonRows rows={8} height={36} />
            </div>
          )}
          {error && <ErrorState error={error} onRetry={reload} />}
          {!loading && !error && data?.length === 0 && (
            <EmptyState icon={Siren} title="No incidents match">
              No incidents match these filters. Incidents open automatically after each analysis run when real evidence meets the criteria.
            </EmptyState>
          )}
          {data?.length > 0 && (
            <table className={s.table}>
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Incident</th>
                  <th>Severity</th>
                  <th className={s.num}>Score</th>
                  <th>Status</th>
                  <th>Persistence</th>
                  <th className={s.num}>Detections</th>
                  <th>Last detection</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((inc) => (
                  <tr key={inc.id} onClick={() => navigate(`/investigation/${inc.id}`)} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && navigate(`/investigation/${inc.id}`)}>
                    <td className={`mono ${s.nowrap}`} style={{ boxShadow: `inset 3px 0 0 ${PRIORITY[inc.priority]?.color}` }}>
                      {inc.reference}
                    </td>
                    <td className={s.wideCell}>
                      <div className={s.strong}>{inc.title}</div>
                      <div className={s.muted}>
                        <ClassificationTag classification={inc.classification} short />
                        {inc.facility_type_label ? ` · ${inc.facility_type_label} · ${fmtDistance(inc.nearest_facility_distance_m)}` : ''}
                      </div>
                    </td>
                    <td>
                      <PriorityBadge priority={inc.priority} />
                    </td>
                    <td className={`${s.num} mono`}>{fmtNum(inc.risk_score, 0)}</td>
                    <td>
                      <Badge tone={inc.status === 'active' ? 'err' : inc.status === 'monitoring' ? 'warn' : 'idle'} variant="outline">
                        {titleCase(inc.status)}
                      </Badge>
                    </td>
                    <td>
                      <PersistenceBadge category={inc.persistence_category} />
                    </td>
                    <td className={`${s.num} mono`}>{fmtInt(inc.observation_count)}</td>
                    <td className={s.nowrap} title={fmtUtc(inc.last_detected_at)}>
                      {fmtRelative(inc.last_detected_at)}
                    </td>
                    <td>
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={MapPin}
                        onClick={(e) => {
                          e.stopPropagation();
                          showOnMap(inc);
                        }}
                      >
                        Map
                      </Button>
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
