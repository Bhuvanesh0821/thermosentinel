import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ExternalLink, Factory, MapPin } from 'lucide-react';
import { useApi } from '../hooks/useApi.js';
import { useApp } from '../state/AppContext.jsx';
import { facilityColor } from '../utils/constants.js';
import { fmtCoord, fmtInt, fmtUtc, titleCase } from '../utils/format.js';
import { Button, EmptyState, ErrorState, Select, SkeletonRows } from '../components/common/ui.jsx';
import s from './page.module.css';
import f from './FacilitiesView.module.css';

const PAGE = 50;

export default function FacilitiesView() {
  const { focusMap, setSelection } = useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get('q') || '');
  const [debounced, setDebounced] = useState(params.get('q') || '');
  const [type, setType] = useState(params.get('type'));
  const [offset, setOffset] = useState(0);
  const types = useApi('/api/facilities/types');
  const list = useApi('/api/facilities', { q: debounced.length >= 2 ? debounced : undefined, type, limit: PAGE, offset });

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);
  useEffect(() => setOffset(0), [debounced, type]);

  const maxCount = Math.max(1, ...(types.data || []).map((t) => t.count));
  const typeOptions = [{ value: null, label: 'All types' }, ...(types.data || []).filter((t) => t.count > 0).map((t) => ({ value: t.facility_type, label: `${t.label} (${fmtInt(t.count)})` }))];

  function locate(fac) {
    setSelection({ type: 'facility', id: fac.id, lon: fac.longitude, lat: fac.latitude });
    focusMap(fac.longitude, fac.latitude, 13);
    navigate('/dashboard');
  }

  return (
    <div className={s.page}>
      <div className={s.header}>
        <div>
          <h1 className={s.title}>Industrial facilities</h1>
          <p className={s.subtitle}>
            Thermally relevant industrial infrastructure inside India's boundary and EEZ, mapped by OpenStreetMap contributors
            (ODbL) and refreshed from the Overpass API. Used for proximity analysis of every thermal cluster.
          </p>
        </div>
      </div>

      <div className={f.layout}>
        <section className={`${s.card} ${f.breakdown}`} aria-label="Facilities by type">
          <h2 className={f.cardTitle}>By type</h2>
          {types.loading && <SkeletonRows rows={8} height={20} gap={10} />}
          {types.error && <ErrorState error={types.error} onRetry={types.reload} compact />}
          {types.data && types.meta?.total === 0 && (
            <EmptyState icon={Factory} title="No facilities ingested yet">
              Run the pipeline to load facilities from OpenStreetMap.
            </EmptyState>
          )}
          {types.data && types.meta?.total > 0 && (
            <ul className={f.bars}>
              {types.data.map((t) => (
                <li key={t.facility_type}>
                  <button
                    type="button"
                    className={f.barRow}
                    aria-pressed={type === t.facility_type}
                    onClick={() => setType(type === t.facility_type ? null : t.facility_type)}
                    disabled={!t.count}
                    title={`${t.label}: ${fmtInt(t.count)} facilities${type === t.facility_type ? ' (click to clear filter)' : ' (click to filter)'}`}
                  >
                    <span className={f.barLabel}>
                      <span className={f.typeDot} style={{ background: facilityColor(t.facility_type) }} />
                      {t.label}
                    </span>
                    <span className={f.barTrack}>
                      {t.count > 0 && <span className={f.barFill} style={{ width: `${Math.max(1.5, (t.count / maxCount) * 100)}%` }} />}
                    </span>
                    <span className={f.barValue}>{fmtInt(t.count)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={`${s.card} ${s.tableCard}`} aria-label="Facility list">
          <div className={f.toolbar}>
            <input className={s.search} type="search" placeholder="Search name or operator…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search facilities" />
            <Select label="Facility type" value={type} onChange={setType} options={typeOptions} />
          </div>
          {list.loading && (
            <div style={{ padding: 12 }}>
              <SkeletonRows rows={10} height={30} />
            </div>
          )}
          {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
          {!list.loading && !list.error && list.data?.length === 0 && (
            <EmptyState icon={Factory} title="No facilities match">
              Adjust the search or type filter.
            </EmptyState>
          )}
          {list.data?.length > 0 && (
            <table className={s.table}>
              <thead>
                <tr>
                  <th>Facility</th>
                  <th>Type</th>
                  <th>Operator</th>
                  <th>Location</th>
                  <th>Source</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.data.map((fac) => (
                  <tr key={fac.id} onClick={() => locate(fac)}>
                    <td>
                      <div className={s.strong}>{fac.name || <span className={s.muted}>Unnamed</span>}</div>
                      {fac.facility_subtype && <div className={s.muted}>{titleCase(fac.facility_subtype)}</div>}
                    </td>
                    <td className={s.nowrap}>
                      <span className={f.typeDot} style={{ background: facilityColor(fac.facility_type) }} />
                      {fac.facility_type_label}
                    </td>
                    <td>{fac.operator || <span className={s.muted}>—</span>}</td>
                    <td className={`mono ${s.nowrap}`} style={{ fontSize: 11.5 }}>
                      {fmtCoord(fac.latitude, fac.longitude, 3)}
                    </td>
                    <td className={s.nowrap} title={`OSM snapshot ${fmtUtc(fac.source_timestamp)}`}>
                      <a href={fac.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className={f.osm}>
                        OSM {fac.source_ref} <ExternalLink size={11} />
                      </a>
                    </td>
                    <td>
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={MapPin}
                        onClick={(e) => {
                          e.stopPropagation();
                          locate(fac);
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
          {list.meta && list.meta.total > 0 && (
            <div className={s.pager}>
              <span>
                {fmtInt(offset + 1)}–{fmtInt(Math.min(offset + PAGE, list.meta.total))} of {fmtInt(list.meta.total)}
              </span>
              <span style={{ display: 'flex', gap: 6 }}>
                <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                  Previous
                </Button>
                <Button size="sm" disabled={offset + PAGE >= list.meta.total} onClick={() => setOffset(offset + PAGE)}>
                  Next
                </Button>
              </span>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
