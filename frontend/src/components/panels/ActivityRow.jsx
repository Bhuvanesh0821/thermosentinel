import BarBreakdown from '../charts/BarBreakdown.jsx';
import TimeSeriesChart, { Legend, hourLabel, hourTitle } from '../charts/TimeSeriesChart.jsx';
import { InlineError, SkeletonRows } from '../common/ui.jsx';
import { useApi } from '../../hooks/useApi.js';
import { useApp } from '../../state/AppContext.jsx';
import { CLASSIFICATION, PRIORITY, PRIORITY_ORDER, WINDOW_OPTIONS } from '../../utils/constants.js';
import s from './ActivityRow.module.css';

// Midnight ticks show the date, other ticks the time (UTC), so a 48 h axis stays unambiguous.
const tickLabel = (v) => {
  const d = new Date(v);
  return d.getUTCHours() === 0 ? d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' }) : hourLabel(v);
};

const DAYNIGHT = [
  { key: 'night', label: 'Night', color: '#2a78d6' },
  { key: 'day', label: 'Day', color: '#eb6834' },
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
 * Dashboard charts next to the map: detection activity over the selected window, open incidents
 * by priority and the mix of event types. Bars act as filters for the map and panels.
 */
export default function ActivityRow() {
  const { filters, setFilters } = useApp();
  const trend = useApi('/api/stats/timeseries', { hours: filters.hours });
  const summary = useApi('/api/stats/summary', { hours: filters.hours });
  const windowLabel = WINDOW_OPTIONS.find((w) => w.value === filters.hours)?.label || `${filters.hours} h`;
  const buckets = trend.data?.buckets || [];
  const inc = summary.data?.incidents;
  const classes = summary.data?.classifications || [];
  const step = trend.data?.bucket_hours;
  const xLabel = step && step >= 24 ? undefined : tickLabel;

  return (
    <div className={s.row}>
      <Card title="Detections over time" sub={`${windowLabel} · per ${trend.data?.bucket || '…'} · UTC`}>
        {trend.error && <InlineError error={trend.error} onRetry={trend.reload} />}
        {trend.loading && <SkeletonRows rows={1} height={150} />}
        {buckets.length > 0 && (
          <>
            <Legend series={DAYNIGHT} noData={buckets.some((b) => b.covered === false)} />
            <TimeSeriesChart
              data={buckets}
              series={DAYNIGHT}
              height={150}
              xKey="bucket"
              {...(xLabel ? { xLabel, xTitle: hourTitle } : {})}
              label={`Satellite detections per ${trend.data.bucket}, day and night, over the last ${windowLabel}`}
            />
          </>
        )}
      </Card>
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
