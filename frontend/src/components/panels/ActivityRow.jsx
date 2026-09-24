import { useState } from 'react';
import AreaTrendChart from '../charts/AreaTrendChart.jsx';
import BarBreakdown from '../charts/BarBreakdown.jsx';
import { SkeletonRows } from '../common/ui.jsx';
import { useApi } from '../../hooks/useApi.js';
import { useApp } from '../../state/AppContext.jsx';
import { CLASSIFICATION, PRIORITY, PRIORITY_ORDER, WINDOW_OPTIONS } from '../../utils/constants.js';
import s from './ActivityRow.module.css';

const TREND_RANGES = [
  { value: 24, label: '24 h' },
  { value: 48, label: '48 h' },
  { value: 72, label: '72 h' },
  { value: 168, label: '7 d' },
];
// Categorical slots 1-3 (validated for colour-vision deficiency); the night line is also dashed.
const TREND_SERIES = [
  { key: 'total', label: 'All detections', color: '#2a78d6', type: 'area' },
  { key: 'industrial', label: 'Industrial-associated', color: '#eb6834', type: 'area' },
  { key: 'night', label: 'Night-time', color: '#1baf7a', type: 'line', dashed: true },
];

export function Card({ title, sub, children }) {
  return (
    <section className={s.card}>
      <header className={s.head}>
        <h2 className={s.title}>{title}</h2>
        {sub && <span className={s.sub}>{sub}</span>}
      </header>
      {children}
    </section>
  );
}

/**
 * Dashboard charts next to the map: thermal activity over time (own time range, scrubbable),
 * open incidents by priority and the mix of event types. Bars act as filters for the map and panels.
 */
export default function ActivityRow() {
  const { filters, setFilters } = useApp();
  const [trendHours, setTrendHours] = useState(48);
  const trend = useApi('/api/stats/timeseries', { hours: trendHours });
  const summary = useApi('/api/stats/summary', { hours: filters.hours });
  const windowLabel = WINDOW_OPTIONS.find((w) => w.value === filters.hours)?.label || `${filters.hours} h`;
  const trendLabel = TREND_RANGES.find((r) => r.value === trendHours)?.label;
  const inc = summary.data?.incidents;
  const classes = summary.data?.classifications || [];

  return (
    <div className={s.row}>
      <div className={s.full}>
        <AreaTrendChart
          title={`Thermal activity · last ${trendLabel}`}
          badge="NASA FIRMS"
          subtitle={trend.data ? `per ${trend.data.bucket} · UTC` : undefined}
          data={trend.data?.buckets}
          series={TREND_SERIES}
          stepHours={trend.data?.bucket_hours || 1}
          ranges={TREND_RANGES}
          range={trendHours}
          onRange={setTrendHours}
          loading={trend.loading}
          error={trend.error?.message}
          emptyText="No satellite detections stored for this window."
        />
      </div>
      <Card title="Open incidents by priority" sub="click: this priority and above">
        {summary.loading && <SkeletonRows rows={4} height={20} gap={8} />}
        {inc && (
          <BarBreakdown
            rows={PRIORITY_ORDER.map((p) => ({
              key: p,
              text: PRIORITY[p].label,
              label: (
                <>
                  <span className={s.dot} style={{ background: PRIORITY[p].color }} />
                  {PRIORITY[p].label}
                </>
              ),
              value: inc[p] || 0,
              color: PRIORITY[p].color,
            }))}
            active={filters.minPriority}
            onSelect={(p) => setFilters((f) => ({ ...f, minPriority: p }))}
            emptyText="No open incidents."
          />
        )}
      </Card>
      <Card title="Event types" sub={`active clusters · ${windowLabel}`}>
        {summary.loading && <SkeletonRows rows={4} height={20} gap={8} />}
        {summary.data && (
          <BarBreakdown
            rows={classes.slice(0, 6).map((c) => ({
              key: c.classification,
              text: c.label,
              label: (
                <>
                  <span className={s.dot} style={{ background: CLASSIFICATION[c.classification]?.color }} />
                  {CLASSIFICATION[c.classification]?.short || c.label}
                </>
              ),
              value: c.count,
            }))}
            active={filters.classification.length === 1 ? filters.classification[0] : null}
            onSelect={(k) => setFilters((f) => ({ ...f, classification: k ? [k] : [] }))}
            emptyText="No analysed clusters in this window."
          />
        )}
      </Card>
    </div>
  );
}
