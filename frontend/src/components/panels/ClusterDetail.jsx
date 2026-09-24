import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Check, Crosshair, ExternalLink, FileSearch } from 'lucide-react';
import { api } from '../../api/client.js';
import { useApi } from '../../hooks/useApi.js';
import { useApp } from '../../state/AppContext.jsx';
import { CLASSIFICATION, PRIORITY, RELATIONSHIP } from '../../utils/constants.js';
import { fmtCoord, fmtDistance, fmtInt, fmtNum, fmtPct, fmtRelative, fmtUtc, titleCase } from '../../utils/format.js';
import { PersistenceBadge, PriorityBadge } from '../common/Badges.jsx';
import { Badge, Button, EmptyState, ErrorState, KeyValue, Meter, SectionLabel, SkeletonRows } from '../common/ui.jsx';
import DetectionHistory from '../charts/DetectionHistory.jsx';
import s from './ClusterDetail.module.css';

const STRENGTH_TONE = { high: 'ok', medium: 'accent', low: 'idle' };

function Section({ label, children, aside }) {
  return (
    <section className={s.section}>
      <div className={s.sectionHead}>
        <SectionLabel>{label}</SectionLabel>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Factors({ factors }) {
  return (
    <ul className={s.factors}>
      {factors.map((f) => (
        <li key={f.key} className={s.factor} data-available={f.available} title={f.note}>
          <div className={s.factorTop}>
            <span className={s.factorLabel}>{f.label}</span>
            <span className={`${s.factorPts} mono`}>{f.available ? `+${fmtNum(f.contribution, 1)}` : 'n/a'}</span>
          </div>
          <Meter value={f.score || 0} color={f.available ? 'var(--ink)' : 'var(--border-strong)'} />
          <div className={s.factorValue}>
            {f.value}
            <span className={s.factorWeight}> · weight {Math.round(f.weight * 100)}%</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function LandCover({ cluster, classes }) {
  if (!cluster.land_cover_status) {
    return <div className={s.muted}>Not yet sampled — land cover is added to the highest-priority clusters first on each analysis run.</div>;
  }
  if (cluster.land_cover_status !== 'ok') {
    return <div className={s.muted}>No WorldCover data at this location ({cluster.land_cover_status}).</div>;
  }
  const byCode = Object.fromEntries((classes || []).map((c) => [String(c.code), c]));
  const entries = Object.entries(cluster.land_cover_fractions || {}).sort((a, b) => b[1] - a[1]);
  return (
    <div className={s.lc}>
      <div className={s.lcBar} role="img" aria-label="Land-cover composition">
        {entries.map(([code, f]) => (
          <span key={code} style={{ width: `${f * 100}%`, background: byCode[code]?.color || '#999' }} title={`${byCode[code]?.name || code}: ${fmtPct(f)}`} />
        ))}
      </div>
      <ul className={s.lcList}>
        {entries.slice(0, 5).map(([code, f]) => (
          <li key={code}>
            <span className={s.lcSwatch} style={{ background: byCode[code]?.color || '#999' }} />
            <span>{byCode[code]?.name || `Class ${code}`}</span>
            <span className="mono">{fmtPct(f)}</span>
          </li>
        ))}
      </ul>
      <div className={s.provenance}>
        ESA WorldCover {cluster.land_cover_dataset} · {cluster.land_cover_radius_m} m radius at ~{fmtNum(cluster.land_cover_resolution_m, 0)} m · tile{' '}
        {cluster.land_cover_tile}
      </div>
    </div>
  );
}

export default function ClusterDetail({ clusterId, incidentId, onBack }) {
  const navigate = useNavigate();
  const { focusMap, pushToast } = useApp();
  const { data: c, error, loading, reload } = useApi(`/api/clusters/${clusterId}`, { observation_limit: 200 });
  const incId = incidentId || c?.incident_id;
  const incident = useApi(incId ? `/api/incidents/${incId}` : null, null, { enabled: Boolean(incId) });
  const classes = useApi('/api/landcover/classes', null, { live: false });
  const [acking, setAcking] = useState(false);

  const intel = c?.intelligence;
  const cls = CLASSIFICATION[c?.classification];
  const pr = PRIORITY[c?.priority];

  async function acknowledgeIncident() {
    setAcking(true);
    try {
      await api.post(`/api/incidents/${incId}/acknowledge`);
      incident.reload();
      pushToast({ tone: 'info', title: 'Incident acknowledged' });
    } catch (e) {
      pushToast({ tone: 'error', title: 'Acknowledge failed', body: e.message });
    } finally {
      setAcking(false);
    }
  }

  return (
    <div className={s.detail}>
      <header className={s.head}>
        <button type="button" className={s.back} onClick={onBack} aria-label="Back to list">
          <ArrowLeft size={16} />
        </button>
        <div className={s.headText}>
          <span className={s.kicker}>
            Thermal cluster <span className="mono">#{clusterId}</span>
            {c?.status && c.status !== 'active' && <> · {titleCase(c.status)}</>}
          </span>
          {incident.data && (
            <span className={s.incRef}>
              <span className="mono">{incident.data.reference}</span> · {titleCase(incident.data.status)}
            </span>
          )}
        </div>
        {c && (
          <Button size="sm" icon={Crosshair} onClick={() => focusMap(c.center_longitude, c.center_latitude, 12)} title="Zoom the map to this event">
            Zoom
          </Button>
        )}
        {incId && (
          <Button size="sm" variant="primary" icon={FileSearch} onClick={() => navigate(`/investigation/${incId}`)}>
            Investigate
          </Button>
        )}
      </header>

      <div className={s.scroll}>
        {loading && (
          <div className={s.pad}>
            <SkeletonRows rows={6} height={54} />
          </div>
        )}
        {error && <ErrorState error={error} onRetry={reload} />}
        {c && (
          <>
            <section className={s.summary} style={{ '--tone': pr?.color || 'var(--border-strong)' }}>
              <div className={s.summaryMain}>
                <div className={s.clsLabel}>
                  <span className={s.clsSwatch} style={{ background: cls?.color || 'var(--idle)' }} />
                  {c.classification_label || 'Not yet analysed'}
                </div>
                <div className={s.badges}>
                  <PriorityBadge priority={c.priority} />
                  {c.evidence_strength && (
                    <Badge tone={STRENGTH_TONE[c.evidence_strength]} title="How many independent evidence lines support the classification">
                      {titleCase(c.evidence_strength)} evidence
                    </Badge>
                  )}
                  <PersistenceBadge category={c.persistence_category} />
                </div>
                <div className={s.location}>
                  <span className="mono">{fmtCoord(c.center_latitude, c.center_longitude)}</span>
                  <span> · extent {fmtDistance(c.extent_radius_m)}</span>
                </div>
              </div>
              <div className={s.score} title="Risk / priority score (0–100)">
                <span className={`${s.scoreValue} mono`}>{c.risk_score != null ? fmtNum(c.risk_score, 0) : '—'}</span>
                <span className={s.scoreMax}>/ 100</span>
              </div>
            </section>

            {incident.data && incident.data.status !== 'closed' && (
              <div className={s.incidentBar}>
                <span>
                  Incident <b className="mono">{incident.data.reference}</b> opened {fmtRelative(incident.data.created_at)}
                  {incident.data.acknowledged_at && <> · acknowledged {fmtRelative(incident.data.acknowledged_at)}</>}
                </span>
                {!incident.data.acknowledged_at && (
                  <Button size="sm" icon={Check} onClick={acknowledgeIncident} disabled={acking}>
                    Acknowledge
                  </Button>
                )}
              </div>
            )}

            {intel ? (
              <>
                <Section label="Why this classification" aside={intel.classifier && <span className={s.engine}>{intel.classifier.kind} · no trained model</span>}>
                  <ul className={s.bullets}>
                    {(intel.classification_rationale || []).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                  {intel.alternatives_rejected?.length > 0 && (
                    <details className={s.alternatives}>
                      <summary>Alternatives considered ({intel.alternatives_rejected.length})</summary>
                      <ul className={`${s.bullets} ${s.caveats}`}>
                        {intel.alternatives_rejected.map((a) => (
                          <li key={a.class}>
                            <b>{a.label}</b> — {a.reason.replace(/^Not selected: /, 'not selected: ')}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </Section>
                <Section label="Evidence">
                  <ul className={s.bullets}>
                    {intel.evidence.map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                  {intel.hypotheses?.length > 0 && (
                    <ul className={`${s.bullets} ${s.hypotheses}`}>
                      {intel.hypotheses.map((h) => (
                        <li key={h}>
                          <b>Hypothesis:</b> {h}
                        </li>
                      ))}
                    </ul>
                  )}
                  <ul className={`${s.bullets} ${s.caveats}`}>
                    {intel.caveats.map((cv) => (
                      <li key={cv}>{cv}</li>
                    ))}
                  </ul>
                </Section>
                <Section label="Score breakdown" aside={<span className={s.engine}>{intel.engine_version}</span>}>
                  <Factors factors={intel.factors} />
                </Section>
              </>
            ) : (
              <EmptyState title="Not yet analysed">This cluster has not been scored by the intelligence engine yet.</EmptyState>
            )}

            <Section label="Industrial context" aside={<span className={s.muted}>{RELATIONSHIP[c.spatial_relationship] || ''}</span>}>
              {c.nearby_facilities?.length ? (
                <ul className={s.facilities}>
                  {c.nearby_facilities.map((f) => (
                    <li key={f.id} className={s.facility}>
                      <span className={`${s.rank} mono`}>{f.rank}</span>
                      <span className={s.facilityMain}>
                        <span className={s.facilityName}>{f.name || `Unnamed ${f.facility_type_label?.toLowerCase()}`}</span>
                        <span className={s.facilityMeta}>
                          {f.facility_type_label}
                          {f.operator ? ` · ${f.operator}` : ''}
                        </span>
                      </span>
                      <span className={s.facilityDist}>
                        <span className="mono">{fmtDistance(f.distance_m)}</span>
                        <span className={s.relationship}>{titleCase(f.relationship)}</span>
                      </span>
                      <a className={s.osm} href={`https://www.openstreetmap.org/${f.source_ref}`} target="_blank" rel="noreferrer" title={`OpenStreetMap ${f.source_ref}`}>
                        <ExternalLink size={13} />
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className={s.muted}>No mapped industrial facility within the search radius. OpenStreetMap coverage may be incomplete.</div>
              )}
              {c.facility_member_share != null && (
                <div className={s.provenance}>{fmtPct(c.facility_member_share)} of this cluster's detections lie within the association radius of the nearest facility.</div>
              )}
            </Section>

            <Section label="Land-cover context">
              <LandCover cluster={c} classes={classes.data} />
            </Section>

            <Section label="Detection history" aside={<span className={s.muted}>{fmtInt(c.observations.length)} shown</span>}>
              <DetectionHistory observations={c.observations} />
            </Section>

            <Section label="Detections">
              <KeyValue
                items={[
                  ['Detections', `${fmtInt(c.observation_count)} over ${c.detection_days} day(s)`],
                  ['Max / mean FRP', `${fmtNum(c.max_frp)} / ${fmtNum(c.avg_frp)} MW`],
                  ['First → last', `${fmtUtc(c.start_time)} → ${fmtUtc(c.end_time)}`],
                  ['Night share', fmtPct(c.night_fraction)],
                  ['Mean confidence', c.mean_confidence != null ? fmtNum(c.mean_confidence, 2) : '—'],
                  ['Sensors', (c.products || []).join(', ')],
                  [
                    'Persistence',
                    c.persistence_category
                      ? `${titleCase(c.persistence_category)} — ${c.persistence_detection_days} of ${c.persistence_coverage_days} days within ${c.persistence_details?.radius_m} m`
                      : '—',
                  ],
                ]}
              />
              <div className={s.tableWrap}>
                <table className={s.table}>
                  <thead>
                    <tr>
                      <th>Acquired (UTC)</th>
                      <th>Satellite</th>
                      <th className={s.num}>FRP</th>
                      <th>Conf.</th>
                      <th>D/N</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.observations.slice(0, 60).map((o) => (
                      <tr key={o.id}>
                        <td className="mono">{fmtUtc(o.acquired_at).replace(' UTC', '')}</td>
                        <td>{o.satellite_name}</td>
                        <td className={`${s.num} mono`}>{fmtNum(o.frp)}</td>
                        <td>{o.confidence_pct != null ? `${o.confidence_pct}%` : titleCase(o.confidence_level || '—')}</td>
                        <td>{o.daynight}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {c.observations.length > 60 && <div className={s.provenance}>Showing 60 most recent of {fmtInt(c.observation_count)} detections.</div>}
            </Section>

            <footer className={s.footer}>
              Sources: NASA FIRMS ({(c.products || []).join(', ')}), OpenStreetMap (ODbL), ESA WorldCover (CC BY 4.0). Analysed{' '}
              {fmtUtc(c.analyzed_at)} by {c.analysis_version || 'ThermoSentinel'}. Inferred from satellite and open data; requires verification.
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
