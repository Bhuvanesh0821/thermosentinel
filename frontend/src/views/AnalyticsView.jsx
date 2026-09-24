import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart3 } from 'lucide-react';
import TimeSeriesChart, { Legend } from '../components/charts/TimeSeriesChart.jsx';
import { ClassificationTag } from '../components/common/Badges.jsx';
import { EmptyState, ErrorState, Segmented, SkeletonRows } from '../components/common/ui.jsx';
import GridMap from '../components/map/GridMap.jsx';
import { useApi } from '../hooks/useApi.js';
import { PERSISTENCE, PRIORITY } from '../utils/constants.js';
import { fmtCoord, fmtInt, fmtNum, fmtPct } from '../utils/format.js';
import s from './page.module.css';
import a from './AnalyticsView.module.css';

const WINDOWS = [
  { value: 7, label: '7 days' },
  { value: 14, label: '14 days' },
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
];
const SERIES_1 = '#2a78d6';
const SERIES_2 = '#eb6834';

const DAYNIGHT = [
  { key: 'night', label: 'Night', color: SERIES_1 },
  { key: 'day_count', label: 'Day', color: SERIES_2 },
];
const FRP = [
  { key: 'frp_median', label: 'Median FRP', color: SERIES_1, shape: 'line' },
  { key: 'frp_p90', label: '90th percentile FRP', color: SERIES_2, shape: 'line' },
];
const INDUSTRIAL = [{ key: 'industrial', label: 'Industrial-associated detections', color: SERIES_1 }];
const PRIORITIES = ['critical', 'high', 'medium', 'low'].map((p) => ({ key: p, label: PRIORITY[p].label, color: PRIORITY[p].color }));

function ChartCard({ title, subtitle, legend, table, children, empty }) {
  const [mode, setMode] = useState('chart');
  return (
    <section className={`${s.card} ${a.card}`}>
      <header className={a.cardHead}>
        <div>
          <h2 className={a.cardTitle}>{title}</h2>
          {subtitle && <p className={a.cardSub}>{subtitle}</p>}
        </div>
        {!empty && table && (
          <Segmented
            label={`${title} view`}
            value={mode}
            onChange={setMode}
            options={[
              { value: 'chart', label: 'Chart' },
              { value: 'table', label: 'Table' },
            ]}
          />
        )}
      </header>
      {empty ? (
        <EmptyState icon={BarChart3} title="No data in this window">
          {empty}
        </EmptyState>
      ) : mode === 'chart' ? (
        <>
          {legend}
          {children}
        </>
      ) : (
        <div className={a.tableWrap}>{table}</div>
      )}
    </section>
  );
}

function DailyTable({ rows, columns }) {
  return (
    <table className={a.table}>
      <thead>
        <tr>
          <th>Date (UTC)</th>
          {columns.map((c) => (
            <th key={c.key} className={a.num}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows
          .slice()
          .reverse()
          .map((r) => (
            <tr key={r.day}>
              <td className="mono">{r.day}</td>
              {r.covered === false ? (
                <td colSpan={columns.length} className={a.muted}>
                  No FIRMS data stored for this day
                </td>
              ) : (
                columns.map((c) => (
                  <td key={c.key} className={`${a.num} mono`}>
                    {r[c.key] == null ? '—' : (c.format || fmtInt)(r[c.key])}
                  </td>
                ))
              )}
            </tr>
          ))}
      </tbody>
    </table>
  );
}

function BarList({ rows, valueKey, labelFor, extra, color = SERIES_1 }) {
  const max = Math.max(1, ...rows.map((r) => Number(r[valueKey]) || 0));
  return (
    <ul className={a.bars}>
      {rows.map((r) => (
        <li key={labelFor(r).key} className={a.barRow} title={`${labelFor(r).text}: ${fmtInt(r[valueKey])}`}>
          <span className={a.barLabel}>{labelFor(r).node}</span>
          <span className={a.barTrack}>
            <span className={a.barFill} style={{ width: `${Math.max(1.5, (Number(r[valueKey]) / max) * 100)}%`, background: color }} />
          </span>
          <span className={`${a.barValue} mono`}>{fmtInt(r[valueKey])}</span>
          {extra && <span className={`${a.barExtra} mono`}>{extra(r)}</span>}
        </li>
      ))}
    </ul>
  );
}

function Kpi({ label, value, note }) {
  return (
    <div className={a.kpi}>
      <div className={a.kpiLabel}>{label}</div>
      <div className={`${a.kpiValue} mono`}>{fmtInt(value)}</div>
      {note && <div className={a.kpiNote}>{note}</div>}
    </div>
  );
}

export default function AnalyticsView() {
  const navigate = useNavigate();
  const [days, setDays] = useState(14);
  const { data, error, loading, refreshing, reload } = useApi('/api/analytics/overview', { days });
  const grid = useApi('/api/analytics/grid', { days, cell: 0.5 });

  const obs = data?.observations_daily || [];
  const inc = data?.incidents_daily || [];
  const covered = obs.filter((d) => d.covered);
  const hasObs = covered.some((d) => d.total > 0);
  const hasFrp = covered.some((d) => d.frp_median != null);
  const hasIndustrial = covered.some((d) => d.industrial > 0);
  const hasIncidents = inc.some((d) => d.total > 0);
  const noDataDays = obs.some((d) => d.covered === false);
  const t = data?.totals;

  return (
    <div className={s.page} data-refreshing={refreshing}>
      <div className={s.header}>
        <div>
          <h1 className={s.title}>Analytics</h1>
          <p className={s.subtitle}>
            Trends computed live from the stored NASA FIRMS detections, clusters and incidents for India (official boundary + EEZ). All
            dates are UTC days.
            {data?.earliest_detection_day && ` Stored detection history starts ${data.earliest_detection_day}.`}
          </p>
        </div>
        <div className={s.controls}>
          <Segmented label="Analysis window" value={days} onChange={setDays} options={WINDOWS} />
        </div>
      </div>

      {loading && <SkeletonRows rows={4} height={180} gap={12} />}
      {error && <ErrorState error={error} onRetry={reload} center />}
      {data && (
        <div className={a.body}>
          <section className={`${s.card} ${a.kpis}`} aria-label="Totals">
            <Kpi label={`Detections · ${days} d`} value={t.detections} />
            <Kpi label="Active clusters" value={t.active_clusters} />
            <Kpi
              label="Industrial-associated"
              value={t.industrial_clusters}
              note={t.active_clusters ? `${fmtPct(t.industrial_clusters / t.active_clusters)} of active clusters` : null}
            />
            <Kpi label="Persistent sources" value={t.persistent_sources} />
            <Kpi label="Open incidents" value={t.open_incidents} />
            <Kpi label="Open alerts" value={t.open_alerts} />
          </section>

          <div className={s.grid2}>
            <ChartCard
              title="Satellite detections per day"
              subtitle="All FIRMS thermal detections inside India, split by overpass time"
              empty={!hasObs && 'No FIRMS detections are stored for this window.'}
              legend={<Legend series={DAYNIGHT} noData={noDataDays} />}
              table={
                <DailyTable
                  rows={obs}
                  columns={[
                    { key: 'total', label: 'Total' },
                    { key: 'day_count', label: 'Day' },
                    { key: 'night', label: 'Night' },
                    { key: 'viirs', label: 'VIIRS' },
                    { key: 'modis', label: 'MODIS' },
                  ]}
                />
              }
            >
              <TimeSeriesChart data={obs} series={DAYNIGHT} label="Detections per day, day and night" />
            </ChartCard>
            <ChartCard
              title="Fire radiative power trend"
              subtitle="Daily median and 90th percentile FRP of detections (MW)"
              empty={!hasFrp && 'No FRP values are stored for this window.'}
              legend={<Legend series={FRP} noData={noDataDays} />}
              table={
                <DailyTable
                  rows={obs}
                  columns={[
                    { key: 'frp_median', label: 'Median MW', format: (v) => fmtNum(v) },
                    { key: 'frp_p90', label: 'P90 MW', format: (v) => fmtNum(v) },
                    { key: 'frp_max', label: 'Max MW', format: (v) => fmtNum(v) },
                  ]}
                />
              }
            >
              <TimeSeriesChart
                data={obs}
                series={FRP}
                type="line"
                unit="MW"
                valueFormat={(v) => fmtNum(v, v >= 10 ? 0 : 1)}
                label="FRP median and 90th percentile per day"
              />
            </ChartCard>
          </div>

          <div className={s.grid2}>
            <ChartCard
              title="Industrial-associated detections"
              subtitle="Detections belonging to clusters inside or adjacent to mapped industrial facilities"
              empty={!hasIndustrial && 'No detections in this window are associated with an industrial facility.'}
              legend={noDataDays ? <Legend series={[]} noData /> : null}
              table={
                <DailyTable
                  rows={obs}
                  columns={[
                    { key: 'industrial', label: 'Industrial' },
                    { key: 'total', label: 'All detections' },
                  ]}
                />
              }
            >
              <TimeSeriesChart data={obs} series={INDUSTRIAL} label="Industrial-associated detections per day" />
            </ChartCard>
            <ChartCard
              title="New incidents by priority"
              subtitle="Incidents by the day of their first satellite detection"
              empty={!hasIncidents && 'No incidents began in this window.'}
              legend={<Legend series={PRIORITIES} noData={inc.some((d) => d.covered === false)} />}
              table={
                <DailyTable
                  rows={inc}
                  columns={[...PRIORITIES.map((p) => ({ key: p.key, label: p.label })), { key: 'total', label: 'Total' }]}
                />
              }
            >
              <TimeSeriesChart data={inc} series={PRIORITIES} label="New incidents per day by priority" />
            </ChartCard>
          </div>

          <ChartCard
            title="Geographic distribution"
            subtitle={`Detections in 0.5° cells over the last ${days} days · hover a cell for details`}
            empty={grid.data && grid.data.features.length === 0 && 'No detections to map for this window.'}
            table={
              grid.data && (
                <table className={a.table}>
                  <thead>
                    <tr>
                      <th>Cell (south-west corner)</th>
                      <th className={a.num}>Detections</th>
                      <th className={a.num}>Clusters</th>
                      <th className={a.num}>Max FRP (MW)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {grid.data.features
                      .slice()
                      .sort((x, y) => y.properties.detections - x.properties.detections)
                      .slice(0, 40)
                      .map((f) => (
                        <tr key={`${f.properties.south}-${f.properties.west}`}>
                          <td className="mono">{fmtCoord(f.properties.south, f.properties.west, 1)}</td>
                          <td className={`${a.num} mono`}>{fmtInt(f.properties.detections)}</td>
                          <td className={`${a.num} mono`}>{fmtInt(f.properties.clusters)}</td>
                          <td className={`${a.num} mono`}>{fmtNum(f.properties.max_frp)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              )
            }
          >
            {grid.error ? <ErrorState error={grid.error} onRetry={grid.reload} /> : <GridMap grid={grid.data} />}
          </ChartCard>

          <div className={s.grid3}>
            <ChartCard
              title="Event classification"
              subtitle="Active clusters by rule-based classification"
              empty={!data.classifications.length && 'No analysed clusters yet.'}
            >
              <BarList
                rows={data.classifications}
                valueKey="clusters"
                labelFor={(r) => ({ key: r.classification, text: r.label, node: <ClassificationTag classification={r.classification} /> })}
              />
            </ChartCard>
            <ChartCard
              title="Facility types near heat"
              subtitle="Industrial-associated active clusters by nearest facility type"
              empty={!data.facility_types.length && 'No industrial-associated clusters yet.'}
            >
              <BarList
                rows={data.facility_types}
                valueKey="clusters"
                labelFor={(r) => ({ key: r.facility_type, text: r.label, node: r.label })}
              />
            </ChartCard>
            <ChartCard
              title="Persistence"
              subtitle="Active clusters by how often the location is re-detected"
              empty={!data.persistence.length && 'Persistence has not been computed yet.'}
            >
              <BarList
                rows={['persistent', 'recurring', 'transient', 'insufficient_history']
                  .map((k) => data.persistence.find((p) => p.category === k))
                  .filter(Boolean)}
                valueKey="clusters"
                labelFor={(r) => ({
                  key: r.category,
                  text: PERSISTENCE[r.category]?.label || r.category,
                  node: PERSISTENCE[r.category]?.label || r.category,
                })}
                extra={(r) => `${fmtInt(r.industrial)} ind.`}
              />
            </ChartCard>
          </div>

          <section className={`${s.card} ${s.tableCard}`}>
            <header className={a.cardHead} style={{ padding: '12px 14px 8px' }}>
              <div>
                <h2 className={a.cardTitle}>Most persistent thermal sources</h2>
                <p className={a.cardSub}>Active persistent clusters ranked by the number of distinct days detected</p>
              </div>
            </header>
            {data.top_persistent_sources.length === 0 ? (
              <EmptyState title="No persistent sources yet">
                Persistence requires the same location to be detected on several distinct days.
              </EmptyState>
            ) : (
              <table className={s.table}>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Classification</th>
                    <th>Facility</th>
                    <th className={s.num}>Days detected</th>
                    <th className={s.num}>Detections</th>
                    <th className={s.num}>Peak FRP</th>
                    <th className={s.num}>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_persistent_sources.map((r) => (
                    <tr key={r.cluster_id} onClick={() => navigate(r.incident_id ? `/investigation/${r.incident_id}` : '/thermal-sources')}>
                      <td>
                        <div className={s.strong}>Cluster #{r.cluster_id}</div>
                        <div className={`mono ${s.muted}`}>{fmtCoord(r.center_latitude, r.center_longitude, 3)}</div>
                      </td>
                      <td>
                        <ClassificationTag classification={r.classification} />
                      </td>
                      <td>
                        {r.facility_name ? (
                          `${r.facility_name} · ${r.facility_type_label}`
                        ) : (
                          <span className={s.muted}>{r.facility_type_label || '—'}</span>
                        )}
                      </td>
                      <td className={`${s.num} mono`}>
                        {r.persistence_detection_days} / {r.persistence_coverage_days}
                      </td>
                      <td className={`${s.num} mono`}>{fmtInt(r.observation_count)}</td>
                      <td className={`${s.num} mono`}>{fmtNum(r.max_frp)} MW</td>
                      <td className={`${s.num} mono`}>{r.risk_score != null ? Math.round(r.risk_score) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
