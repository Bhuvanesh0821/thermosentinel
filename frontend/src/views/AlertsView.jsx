import { Fragment, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BellRing, Check, ChevronDown, CircleCheck, FileSearch, Search } from 'lucide-react';
import { api } from '../api/client.js';
import { PriorityBadge } from '../components/common/Badges.jsx';
import { Badge, Button, EmptyState, ErrorState, Segmented, Select, SkeletonRows } from '../components/common/ui.jsx';
import BarBreakdown from '../components/charts/BarBreakdown.jsx';
import { Card } from '../components/panels/ActivityRow.jsx';
import { RULE_LABELS } from '../components/panels/AlertList.jsx';
import { useApi } from '../hooks/useApi.js';
import { useApp } from '../state/AppContext.jsx';
import { PRIORITY, PRIORITY_ORDER } from '../utils/constants.js';
import { fmtCoord, fmtInt, fmtRelative, fmtUtc, titleCase } from '../utils/format.js';
import s from './page.module.css';
import a from './AlertsView.module.css';

const STATUS_TONE = { open: 'err', acknowledged: 'warn', resolved: 'ok' };
const PAGE = 50;

function AlertEvidence({ alertId }) {
  const { data, error, loading } = useApi(`/api/alerts/${alertId}`, null, { live: false });
  if (loading) return <SkeletonRows rows={2} height={20} />;
  if (error) return <ErrorState error={error} compact />;
  const ev = data.evidence || {};
  return (
    <div className={a.evidence}>
      <div>
        <h4 className={a.evTitle}>Rules that fired</h4>
        <table className={a.ruleTable}>
          <thead>
            <tr>
              <th>Rule</th>
              <th>Measured</th>
              <th>Threshold</th>
            </tr>
          </thead>
          <tbody>
            {(ev.rules || []).map((r) => (
              <tr key={r.key}>
                <td>
                  <b>{r.label}</b>
                  <div className={s.muted}>{r.detail}</div>
                </td>
                <td className="mono">{String(r.value)}</td>
                <td className="mono">{String(r.threshold)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>
        <h4 className={a.evTitle}>Underlying event</h4>
        <ul className={a.evList}>
          <li>
            {ev.classification_label} · intelligence score <b className="mono">{Math.round(ev.intelligence_score ?? 0)}</b>/100 · risk{' '}
            {ev.risk_level}
          </li>
          {(ev.evidence || []).map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
        {data.location && <div className={s.muted}>Location {fmtCoord(data.location.latitude, data.location.longitude)}</div>}
        <div className={s.muted}>Source: {data.source}</div>
        {data.notifications?.length > 0 && (
          <div className={s.muted}>Delivered: {data.notifications.map((n) => `${n.channel} (${n.event}, ${n.status})`).join(' · ')}</div>
        )}
        {data.resolution && <div className={s.muted}>Resolution: {data.resolution}</div>}
      </div>
    </div>
  );
}

export default function AlertsView() {
  const navigate = useNavigate();
  const { pushToast } = useApp();
  const [status, setStatus] = useState('open');
  const [severity, setSeverity] = useState(null);
  const [rule, setRule] = useState(null);
  const [query, setQuery] = useState('');
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState(null);
  const [busy, setBusy] = useState(null);
  const rules = useApi('/api/alerts/rules', null, { live: false });
  useEffect(() => {
    const t = setTimeout(() => setQ(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);
  useEffect(() => setOffset(0), [status, severity, rule, q]);
  const { data, meta, error, loading, refreshing, reload } = useApi('/api/alerts', {
    status: status === 'all' ? undefined : status,
    min_severity: severity,
    rule,
    q: q.length >= 2 ? q : undefined,
    limit: PAGE,
    offset,
    breakdown: true,
  });
  const counts = meta?.by_status || {};
  const bd = meta?.breakdown;

  async function act(alert, action) {
    setBusy(alert.id);
    try {
      await api.post(
        `/api/alerts/${alert.id}/${action}`,
        null,
        action === 'resolve' ? { note: 'Resolved by operator from the alert centre' } : undefined,
      );
      reload();
    } catch (e) {
      pushToast({ tone: 'error', title: `Could not ${action} alert`, body: e.message });
    } finally {
      setBusy(null);
    }
  }

  const statusTabs = [
    { value: 'open', label: `Open${counts.open ? ` · ${counts.open}` : ''}` },
    { value: 'acknowledged', label: `Acknowledged${counts.acknowledged ? ` · ${counts.acknowledged}` : ''}` },
    { value: 'resolved', label: `Resolved${counts.resolved ? ` · ${counts.resolved}` : ''}` },
    { value: 'all', label: 'All' },
  ];

  return (
    <div className={s.page}>
      <div className={s.header}>
        <div>
          <h1 className={s.title}>Alert centre</h1>
          <p className={s.subtitle}>
            Generated by the rule engine only from real incident evidence - one alert per underlying event, updated or escalated as new
            evidence arrives and resolved automatically when the incident closes.
            {rules.data && ` Minimum severity: ${rules.data.min_alert_severity}.`}
          </p>
        </div>
      </div>
      {bd && meta.total > 0 && (
        <div className={s.grid2} style={{ marginBottom: 12 }}>
          <Card title="By severity" sub={`${fmtInt(meta.total)} alerts matching the filters`}>
            <BarBreakdown
              rows={PRIORITY_ORDER.map((p) => ({
                key: p,
                text: PRIORITY[p].label,
                label: (
                  <>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: PRIORITY[p].color, flex: 'none' }} />
                    {PRIORITY[p].label}
                  </>
                ),
                value: bd.by_severity[p] || 0,
                color: PRIORITY[p].color,
              }))}
            />
          </Card>
          <Card title="Rules that fired" sub="an alert can meet several rules · click to filter">
            <BarBreakdown
              rows={Object.entries(RULE_LABELS)
                .map(([key, label]) => ({ key, text: label, label, value: bd.by_rule[key] || 0 }))
                .sort((x, y) => y.value - x.value)}
              total={meta.total}
              active={rule}
              onSelect={setRule}
            />
          </Card>
        </div>
      )}
      <div className={`${s.card} ${s.tableCard}`} data-refreshing={refreshing}>
        <div className={s.tableToolbar}>
          <Segmented options={statusTabs} value={status} onChange={setStatus} label="Alert status" />
          <Select
            label="Minimum severity"
            value={severity}
            onChange={setSeverity}
            options={[
              { value: null, label: 'Any severity' },
              ...PRIORITY_ORDER.slice()
                .reverse()
                .map((p) => ({ value: p, label: `${PRIORITY[p].label} +` })),
            ]}
          />
          <Select
            label="Rule"
            value={rule}
            onChange={setRule}
            options={[{ value: null, label: 'Any rule' }, ...Object.entries(RULE_LABELS).map(([value, label]) => ({ value, label }))]}
          />
          <label className={s.searchWrap}>
            <Search size={14} />
            <input
              className={s.search}
              type="search"
              placeholder="Search alerts…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search alerts"
            />
          </label>
          {meta && <span className={s.muted}>{fmtInt(meta.total)} alerts</span>}
        </div>
        {loading && (
          <div style={{ padding: 12 }}>
            <SkeletonRows rows={6} height={40} />
          </div>
        )}
        {error && <ErrorState error={error} onRetry={reload} />}
        {!loading && !error && data?.length === 0 && (
          <EmptyState icon={BellRing} title="No alerts match">
            Alerts appear here when a rule fires on a real incident at or above the minimum severity.
          </EmptyState>
        )}
        {data?.length > 0 && (
          <table className={s.table}>
            <thead>
              <tr>
                <th style={{ width: 28 }} />
                <th>Alert</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Rules</th>
                <th>Last evidence</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((al) => (
                <Fragment key={al.id}>
                  <tr onClick={() => setExpanded(expanded === al.id ? null : al.id)} aria-expanded={expanded === al.id}>
                    <td style={{ boxShadow: `inset 3px 0 0 ${PRIORITY[al.severity]?.color}` }}>
                      <ChevronDown
                        size={14}
                        style={{ transform: expanded === al.id ? 'rotate(180deg)' : 'none', color: 'var(--text-3)' }}
                      />
                    </td>
                    <td className={a.titleCell}>
                      <div className={s.strong}>{al.title}</div>
                      <div className={s.muted}>
                        {al.facility
                          ? `${al.facility.name || 'Unnamed facility'} · ${al.facility.type_label}`
                          : al.location
                            ? fmtCoord(al.location.latitude, al.location.longitude, 3)
                            : '—'}
                        {' · '}#{al.id}
                        {al.escalation_count ? ` · escalated ${al.escalation_count}×` : ''}
                      </div>
                    </td>
                    <td>
                      <PriorityBadge priority={al.severity} />
                    </td>
                    <td>
                      <Badge tone={STATUS_TONE[al.status]} variant="outline">
                        {titleCase(al.status)}
                      </Badge>
                    </td>
                    <td>
                      <div className={a.rules}>
                        {(al.rules || []).map((r) => (
                          <span key={r} className={a.rule}>
                            {RULE_LABELS[r] || r}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className={s.nowrap} title={`Raised ${fmtUtc(al.created_at)} · last evidence ${fmtUtc(al.last_triggered_at)}`}>
                      {fmtRelative(al.last_triggered_at)}
                      <div className={s.muted}>raised {fmtRelative(al.created_at)}</div>
                    </td>
                    <td className={s.nowrap} onClick={(e) => e.stopPropagation()}>
                      <span style={{ display: 'inline-flex', gap: 4 }}>
                        {al.status === 'open' && (
                          <Button size="sm" icon={Check} disabled={busy === al.id} onClick={() => act(al, 'acknowledge')}>
                            Ack
                          </Button>
                        )}
                        {al.status !== 'resolved' && (
                          <Button size="sm" variant="ghost" icon={CircleCheck} disabled={busy === al.id} onClick={() => act(al, 'resolve')}>
                            Resolve
                          </Button>
                        )}
                        {al.incident_id && (
                          <Button size="sm" variant="ghost" icon={FileSearch} onClick={() => navigate(`/investigation/${al.incident_id}`)}>
                            Investigate
                          </Button>
                        )}
                      </span>
                    </td>
                  </tr>
                  {expanded === al.id && (
                    <tr className={a.expandRow}>
                      <td />
                      <td colSpan={6}>
                        <AlertEvidence alertId={al.id} />
                      </td>
                    </tr>
                  )}
                </Fragment>
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
  );
}
