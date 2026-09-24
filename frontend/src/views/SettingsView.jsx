import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { BellRing, Cpu, Database, HeartPulse, ShieldCheck } from 'lucide-react';
import { StatusBadge } from '../components/common/Badges.jsx';
import { Badge, Button, ErrorState, SkeletonRows } from '../components/common/ui.jsx';
import { useApi } from '../hooks/useApi.js';
import { useApp } from '../state/AppContext.jsx';
import { STATUS_TONE } from '../utils/constants.js';
import { fmtRelative, fmtUtc, titleCase } from '../utils/format.js';
import DataSourcesView from './DataSourcesView.jsx';
import s from './page.module.css';
import st from './SettingsView.module.css';

const TABS = [
  { value: 'health', label: 'System health', icon: HeartPulse },
  { value: 'sources', label: 'Data sources & pipeline', icon: Database },
  { value: 'notifications', label: 'Notifications', icon: BellRing },
  { value: 'rules', label: 'Alert rules', icon: ShieldCheck },
  { value: 'model', label: 'Intelligence model', icon: Cpu },
];
const HEALTH_LABEL = { connected: 'Connected', degraded: 'Degraded', unavailable: 'Unavailable' };

function Block({ title, subtitle, children, aside }) {
  return (
    <section className={`${s.card} ${st.block}`}>
      <header className={st.blockHead}>
        <div>
          <h2 className={st.blockTitle}>{title}</h2>
          {subtitle && <p className={st.blockSub}>{subtitle}</p>}
        </div>
        {aside}
      </header>
      {children}
    </section>
  );
}

function HealthTab() {
  const { data, error, loading, reload, refreshing } = useApi('/api/system/health', null, { interval: 30000 });
  if (loading) return <SkeletonRows rows={6} height={56} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  return (
    <Block
      title="Component health"
      subtitle="Each component is checked live or from its latest recorded run. Refreshes every 30 seconds."
      aside={
        <div className={st.overall}>
          <span className={s.muted}>Overall</span>
          <Badge tone={STATUS_TONE[data.status]}>{HEALTH_LABEL[data.status] || titleCase(data.status)}</Badge>
          <Button size="sm" variant="ghost" onClick={reload} disabled={refreshing}>
            Re-check
          </Button>
        </div>
      }
    >
      <ul className={st.health}>
        {data.components.map((c) => (
          <li key={c.key} className={st.healthRow} data-status={c.status}>
            <span className={st.healthDot} />
            <div className={st.healthMain}>
              <div className={st.healthLabel}>{c.label}</div>
              <div className={s.muted}>{c.detail}</div>
            </div>
            <span className={`${st.healthTime} ${s.muted}`} title={fmtUtc(c.checked_at)}>
              {c.latency_ms != null && <span className="mono">{c.latency_ms} ms · </span>}
              checked {fmtRelative(c.checked_at)}
            </span>
            <Badge tone={STATUS_TONE[c.status]}>{HEALTH_LABEL[c.status] || titleCase(c.status)}</Badge>
          </li>
        ))}
      </ul>
    </Block>
  );
}

function NotificationsTab() {
  const { browserNotify, setBrowserNotify, pushToast } = useApp();
  const { data, error, loading, reload } = useApi('/api/notifications/channels', null, { live: false });
  const permission = typeof Notification !== 'undefined' ? Notification.permission : 'unsupported';
  const [perm, setPerm] = useState(permission);

  async function toggleBrowser() {
    if (perm === 'unsupported') return;
    if (browserNotify) {
      setBrowserNotify(false);
      return;
    }
    const result = perm === 'granted' ? 'granted' : await Notification.requestPermission();
    setPerm(result);
    setBrowserNotify(result === 'granted');
    if (result !== 'granted')
      pushToast({
        tone: 'info',
        title: 'Browser notifications blocked',
        body: 'Allow notifications for this site in your browser settings.',
      });
  }

  return (
    <div className={s.stack}>
      <Block
        title="Delivery channels"
        subtitle="Credentials for webhook and e-mail stay on the server (environment variables) and are never sent to the browser."
      >
        {loading && <SkeletonRows rows={4} height={48} />}
        {error && <ErrorState error={error} onRetry={reload} compact />}
        {data && (
          <table className={st.table}>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Status</th>
                <th>Configuration</th>
                <th>Minimum severity</th>
                <th>Last delivery</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.channel}>
                  <td className={s.strong}>{c.label}</td>
                  <td>
                    <StatusBadge status={c.status} />
                  </td>
                  <td className={s.muted}>{c.detail}</td>
                  <td>{c.min_severity ? titleCase(c.min_severity) : <span className={s.muted}>All alerts</span>}</td>
                  <td className={s.muted}>
                    {c.last_delivery_at ? (
                      <span title={fmtUtc(c.last_delivery_at)}>
                        {titleCase(c.last_delivery_status)} · {fmtRelative(c.last_delivery_at)}
                      </span>
                    ) : (
                      'None yet'
                    )}
                    {c.last_error && <div className={st.err}>{c.last_error}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Block>
      <Block
        title="Browser notifications on this device"
        subtitle="Shown for new and escalated alerts while the dashboard is open. The preference is stored in this browser only."
      >
        <div className={st.browserRow}>
          <div>
            <div className={s.strong}>{browserNotify && perm === 'granted' ? 'Enabled' : 'Disabled'}</div>
            <div className={s.muted}>
              Browser permission:{' '}
              {perm === 'unsupported' ? 'not supported by this browser' : perm === 'default' ? 'not yet requested' : perm}
            </div>
          </div>
          <Button
            variant={browserNotify ? undefined : 'primary'}
            onClick={toggleBrowser}
            disabled={perm === 'unsupported' || (perm === 'denied' && !browserNotify)}
          >
            {browserNotify ? 'Disable' : 'Enable browser notifications'}
          </Button>
        </div>
      </Block>
    </div>
  );
}

function RulesTab() {
  const { data, error, loading, reload } = useApi('/api/alerts/rules', null, { live: false });
  if (loading) return <SkeletonRows rows={6} height={40} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  return (
    <Block
      title="Alert rules"
      subtitle={`Alerts are raised for incidents at or above ${titleCase(data.min_alert_severity)} severity (incident threshold: intelligence score ≥ ${data.incident_min_score}). Thresholds are set by server environment variables.`}
    >
      <table className={st.table}>
        <thead>
          <tr>
            <th>Rule</th>
            <th>Condition</th>
            <th>Effect</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {data.rules.map((r) => (
            <tr key={r.key}>
              <td>
                <div className={s.strong}>{r.label}</div>
                <div className={`mono ${s.muted}`}>{r.key}</div>
              </td>
              <td>{r.condition}</td>
              <td className={s.muted}>{r.raises_severity ? 'Triggers; can raise severity by one level' : 'Triggers / adds evidence'}</td>
              <td>
                <Badge tone={r.enabled ? 'ok' : 'idle'}>{r.enabled ? 'Enabled' : 'Disabled'}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className={st.notes}>
        <dt>Deduplication</dt>
        <dd>{data.deduplication}</dd>
        <dt>Resolution</dt>
        <dd>{data.resolution}</dd>
      </dl>
    </Block>
  );
}

function ModelTab() {
  const { data, error, loading, reload } = useApi('/api/intelligence/model', null, { live: false });
  if (loading) return <SkeletonRows rows={6} height={40} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  const weights = Object.entries(data.factor_weights).sort((x, y) => y[1] - x[1]);
  return (
    <div className={s.grid2}>
      <Block title="Classifier" subtitle={data.note}>
        <dl className={st.notes}>
          <dt>Engine</dt>
          <dd className="mono">{data.engine_version}</dd>
          <dt>Classifier</dt>
          <dd>
            <span className="mono">{data.classifier.name}</span> v{data.classifier.version} · {data.classifier.kind}
          </dd>
          <dt>Trained model</dt>
          <dd>{data.classifier.trained_model ? 'Yes' : 'No — transparent rules only'}</dd>
        </dl>
        <h3 className={st.subhead}>Event classes</h3>
        <ul className={st.classes}>
          {Object.entries(data.classes).map(([k, label]) => (
            <li key={k}>
              <span>{label}</span>
              <span className={`mono ${s.muted}`}>{k}</span>
            </li>
          ))}
        </ul>
      </Block>
      <Block
        title="Intelligence score factors"
        subtitle="Weights of the explainable 0–100 intelligence score. Missing evidence is excluded and the remaining weights renormalised."
      >
        <ul className={st.weights}>
          {weights.map(([k, w]) => (
            <li key={k}>
              <span>{titleCase(k)}</span>
              <span className={st.wTrack}>
                <span className={st.wFill} style={{ width: `${(w / weights[0][1]) * 100}%` }} />
              </span>
              <span className="mono">{Math.round(w * 100)}%</span>
            </li>
          ))}
        </ul>
      </Block>
    </div>
  );
}

export default function SettingsView() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some((t) => t.value === params.get('tab')) ? params.get('tab') : 'health';

  return (
    <div className={s.page}>
      <div className={s.header}>
        <div>
          <h1 className={s.title}>Settings & system</h1>
          <p className={s.subtitle}>
            Health of every component, data sources, notification channels, alert rules and the intelligence model in use.
          </p>
        </div>
      </div>
      <nav className={st.tabs} aria-label="Settings sections">
        {TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            className={st.tab}
            aria-current={tab === t.value ? 'page' : undefined}
            onClick={() => setParams({ tab: t.value }, { replace: true })}
          >
            <t.icon size={15} />
            {t.label}
          </button>
        ))}
      </nav>
      {tab === 'health' && <HealthTab />}
      {tab === 'sources' && <DataSourcesView embedded />}
      {tab === 'notifications' && <NotificationsTab />}
      {tab === 'rules' && <RulesTab />}
      {tab === 'model' && <ModelTab />}
    </div>
  );
}
