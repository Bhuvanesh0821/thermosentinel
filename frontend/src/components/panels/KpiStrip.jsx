import { useApi } from '../../hooks/useApi.js';
import { useApp } from '../../state/AppContext.jsx';
import { WINDOW_OPTIONS } from '../../utils/constants.js';
import { fmtInt, fmtNum, fmtRelative, fmtUtc } from '../../utils/format.js';
import { InlineError, Skeleton } from '../common/ui.jsx';
import ActivityTrend from '../charts/ActivityTrend.jsx';
import s from './KpiStrip.module.css';

function Kpi({ label, value, sub, tone, title, loading, chart }) {
  return (
    <div className={s.kpi} data-tone={tone} title={title} data-wide={Boolean(chart)}>
      <div className={s.kpiText}>
        <div className={s.label}>{label}</div>
        {loading ? <Skeleton width="60%" height={22} style={{ margin: '3px 0 4px' }} /> : <div className={s.value}>{value}</div>}
        <div className={s.sub}>{loading ? <Skeleton width="80%" height={10} /> : sub}</div>
      </div>
      {chart && <div className={s.kpiChart}>{chart}</div>}
    </div>
  );
}

export default function KpiStrip() {
  const { filters } = useApp();
  const { data, error, loading, reload } = useApi('/api/stats/summary', { hours: filters.hours });
  const trend = useApi('/api/stats/timeseries', { hours: filters.hours }, { enabled: !error });
  const windowLabel = WINDOW_OPTIONS.find((w) => w.value === filters.hours)?.label || `${filters.hours} h`;

  if (error) {
    return (
      <div className={`${s.strip} ${s.errorStrip}`}>
        <InlineError error={error} onRetry={reload} />
      </div>
    );
  }

  const d = data?.detections;
  const c = data?.clusters;
  const i = data?.incidents;
  const a = data?.alerts;
  const openIncidents = i ? i.active + i.monitoring : null;
  const firmsRun = data?.last_runs?.firms_ingest;

  return (
    <div className={s.strip}>
      <Kpi
        loading={loading}
        label={`Detections · ${windowLabel}`}
        value={fmtInt(d?.total)}
        sub={d ? `VIIRS ${fmtInt(d.viirs)} · MODIS ${fmtInt(d.modis)} · night ${fmtInt(d.night)}` : ''}
        chart={
          trend.data?.buckets?.some((b) => b.covered) ? (
            <ActivityTrend series={trend.data} label={`Detections per ${trend.data.bucket} over the last ${windowLabel}`} />
          ) : null
        }
      />
      <Kpi
        loading={loading}
        label="Active clusters"
        value={fmtInt(c?.active)}
        sub={c ? `${fmtInt(c.multi_detection)} multi-detection · ${fmtInt(c.persistent)} persistent` : ''}
        title="Spatio-temporal clusters with a detection in the window"
      />
      <Kpi
        loading={loading}
        label="Industry-linked"
        value={fmtInt(c?.industrial_associated)}
        tone={c?.industrial_associated ? 'high' : undefined}
        sub={c && c.active ? `${fmtNum((c.industrial_associated / c.active) * 100, 1)}% of active clusters` : 'within 3 km of a mapped facility'}
      />
      <Kpi
        loading={loading}
        label="Open incidents"
        value={fmtInt(openIncidents)}
        tone={i?.critical ? 'critical' : i?.high ? 'high' : undefined}
        sub={i ? `${i.critical} critical · ${i.high} high · ${i.medium} medium` : ''}
      />
      <Kpi
        loading={loading}
        label="Open alerts"
        value={fmtInt(a?.open)}
        tone={a?.open ? 'medium' : undefined}
        sub={a ? `${fmtInt(a.last_24h)} raised in last 24 h` : ''}
      />
      <Kpi
        loading={loading}
        label="Facilities"
        value={fmtInt(data?.facilities)}
        sub={
          firmsRun
            ? `FIRMS ingest ${fmtRelative(firmsRun.finished_at || firmsRun.started_at)}`
            : 'No FIRMS ingestion yet'
        }
        title={firmsRun ? `Last FIRMS ingestion: ${fmtUtc(firmsRun.finished_at || firmsRun.started_at)} (${firmsRun.status})` : undefined}
      />
    </div>
  );
}
