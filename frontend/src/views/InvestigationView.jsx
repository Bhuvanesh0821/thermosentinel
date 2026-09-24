import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, BellRing, Check, ExternalLink, FileSearch, MapPin } from 'lucide-react';
import { api } from '../api/client.js';
import DetectionHistory from '../components/charts/DetectionHistory.jsx';
import { PersistenceBadge, PriorityBadge, StatusBadge } from '../components/common/Badges.jsx';
import { Badge, Button, EmptyState, ErrorState, KeyValue, SkeletonRows } from '../components/common/ui.jsx';
import InvestigationMap from '../components/map/InvestigationMap.jsx';
import { RULE_LABELS } from '../components/panels/AlertList.jsx';
import { Factors, LandCover } from '../components/panels/ClusterDetail.jsx';
import { useApi } from '../hooks/useApi.js';
import { useApp } from '../state/AppContext.jsx';
import { CLASSIFICATION, PRIORITY, RELATIONSHIP } from '../utils/constants.js';
import { fmtCoord, fmtDistance, fmtInt, fmtNum, fmtPct, fmtRelative, fmtUtc, titleCase } from '../utils/format.js';
import s from './page.module.css';
import v from './InvestigationView.module.css';

const STRENGTH_TONE = { high: 'ok', medium: 'accent', low: 'idle' };
const ALERT_TONE = { open: 'err', acknowledged: 'warn', resolved: 'ok' };
const OBS_PAGE = 100;

function Card({ title, aside, children, className = '' }) {
  return (
    <section className={`${s.card} ${v.card} ${className}`}>
      <header className={v.cardHead}>
        <h2 className={v.cardTitle}>{title}</h2>
        {aside}
      </header>
      <div className={v.cardBody}>{children}</div>
    </section>
  );
}

function Timeline({ events }) {
  if (!events?.length) return <div className={s.muted}>No events recorded.</div>;
  return (
    <ol className={v.timeline}>
      {events.map((e, i) => (
        <li key={`${e.at}-${i}`} className={v.tlItem} data-kind={e.kind}>
          <span className={v.tlDot} />
          <div className={v.tlBody}>
            <div className={v.tlTitle}>{e.title}</div>
            {e.detail && <div className={s.muted}>{e.detail}</div>}
          </div>
          <time className={`${v.tlTime} mono`} dateTime={e.at}>
            {e.kind === 'daily' ? e.day : fmtUtc(e.at)}
          </time>
        </li>
      ))}
    </ol>
  );
}

export default function InvestigationView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { focusMap, setSelection, pushToast } = useApp();
  const { data, error, loading, reload } = useApi(`/api/investigations/${id}`);
  const classes = useApi('/api/landcover/classes', null, { live: false });
  const [busy, setBusy] = useState(false);
  const [obsShown, setObsShown] = useState(OBS_PAGE);

  if (loading) {
    return (
      <div className={s.page}>
        <SkeletonRows rows={3} height={120} gap={12} />
      </div>
    );
  }
  if (error) {
    return (
      <div className={s.page}>
        <Link to="/incidents" className={v.back}>
          <ArrowLeft size={14} /> Incidents
        </Link>
        <ErrorState error={error} onRetry={reload} center />
      </div>
    );
  }
  const {
    incident: inc,
    classification: cls,
    intelligence: intel,
    cluster,
    facility,
    observations,
    daily,
    satellites,
    alerts,
    timeline,
    provenance,
  } = data;
  const pr = PRIORITY[inc.priority];
  const clsMeta = CLASSIFICATION[cls.key];

  async function acknowledge() {
    setBusy(true);
    try {
      await api.post(`/api/incidents/${inc.id}/acknowledge`);
      pushToast({ tone: 'info', title: `Incident ${inc.reference} acknowledged` });
      reload();
    } catch (e) {
      pushToast({ tone: 'error', title: 'Acknowledge failed', body: e.message });
    } finally {
      setBusy(false);
    }
  }

  function showOnMap() {
    setSelection({ type: 'cluster', id: inc.cluster_id, incidentId: inc.id });
    focusMap(inc.longitude, inc.latitude, 12);
    navigate('/dashboard');
  }

  return (
    <div className={s.page}>
      <Link to="/incidents" className={v.back}>
        <ArrowLeft size={14} /> Incidents
      </Link>
      <header className={v.hero} style={{ '--tone': pr?.color }}>
        <div className={v.heroMain}>
          <div className={v.kicker}>
            <FileSearch size={13} /> Investigation · <span className="mono">{inc.reference}</span> · cluster{' '}
            <span className="mono">#{inc.cluster_id}</span>
          </div>
          <h1 className={v.heroTitle}>{inc.title}</h1>
          <div className={v.badges}>
            <PriorityBadge priority={inc.priority} />
            <StatusBadge status={inc.status} />
            <Badge tone="idle">
              <span className={v.swatch} style={{ background: clsMeta?.color || 'var(--idle)' }} />
              {cls.label}
            </Badge>
            {cls.evidence_strength && (
              <Badge tone={STRENGTH_TONE[cls.evidence_strength]}>{titleCase(cls.evidence_strength)} evidence</Badge>
            )}
            <PersistenceBadge category={cluster.persistence_category} />
          </div>
          <div className={v.heroMeta}>
            <span className="mono">{fmtCoord(inc.latitude, inc.longitude)}</span>
            <span>First detected {fmtUtc(inc.first_detected_at)}</span>
            <span>
              Last detected {fmtUtc(inc.last_detected_at)} ({fmtRelative(inc.last_detected_at)})
            </span>
            {inc.acknowledged_at && <span>Acknowledged {fmtRelative(inc.acknowledged_at)}</span>}
          </div>
        </div>
        <div className={v.heroSide}>
          <div className={v.score} title="Intelligence score (0–100)">
            <span className={`${v.scoreValue} mono`}>{intel.intelligence_score != null ? Math.round(intel.intelligence_score) : '—'}</span>
            <span className={v.scoreMax}>/ 100 intelligence score</span>
          </div>
          <div className={v.actions}>
            {!inc.acknowledged_at && inc.status !== 'closed' && (
              <Button icon={Check} onClick={acknowledge} disabled={busy}>
                Acknowledge
              </Button>
            )}
            <Button variant="primary" icon={MapPin} onClick={showOnMap}>
              Show on map
            </Button>
          </div>
        </div>
      </header>

      <div className={v.body}>
        <div className={v.topGrid}>
          <section className={`${s.card} ${v.mapCard}`} aria-label="Incident map">
            <InvestigationMap observations={observations} cluster={cluster} facility={facility} />
          </section>
          <Card title="Event facts">
            <KeyValue
              items={[
                ['Detections', `${fmtInt(cluster.observation_count)} over ${cluster.detection_days} day(s)`],
                ['Peak / mean FRP', `${fmtNum(cluster.max_frp)} / ${fmtNum(cluster.avg_frp)} MW`],
                ['Total FRP', cluster.total_frp != null ? `${fmtNum(cluster.total_frp, 0)} MW` : '—'],
                ['Max brightness', cluster.max_brightness != null ? `${fmtNum(cluster.max_brightness, 0)} K` : '—'],
                ['Extent', fmtDistance(cluster.extent_radius_m)],
                ['Night share', fmtPct(cluster.night_fraction)],
                ['Mean confidence', cluster.mean_confidence != null ? fmtNum(cluster.mean_confidence, 2) : '—'],
                [
                  'Persistence',
                  cluster.persistence_category
                    ? `${titleCase(cluster.persistence_category)} · ${cluster.persistence_detection_days} of ${cluster.persistence_coverage_days} days`
                    : '—',
                ],
                ['Spatial relation', RELATIONSHIP[cluster.spatial_relationship] || '—'],
                ['Facility distance', fmtDistance(cluster.nearest_facility_distance_m)],
              ]}
            />
            {facility ? (
              <div className={v.facility}>
                <div className={v.facName}>{facility.name || `Unnamed ${facility.type_label?.toLowerCase()}`}</div>
                <div className={s.muted}>
                  {facility.type_label}
                  {facility.operator ? ` · ${facility.operator}` : ''}
                  {facility.footprint_area_m2 ? ` · footprint ${fmtNum(facility.footprint_area_m2 / 10000, 1)} ha` : ''}
                </div>
                <a href={facility.source_url} target="_blank" rel="noreferrer" className={v.link}>
                  OpenStreetMap {facility.source_ref} <ExternalLink size={11} />
                </a>
              </div>
            ) : (
              <div className={`${v.facility} ${s.muted}`}>No mapped industrial facility is associated with this event.</div>
            )}
          </Card>
        </div>

        <div className={s.grid2}>
          <Card title="Detection history" aside={<span className={s.muted}>FRP per detection · UTC</span>}>
            <DetectionHistory observations={observations} />
          </Card>
          <Card title="Daily activity" aside={<span className={s.muted}>{daily.length} day(s)</span>}>
            <div className={v.scrollTable}>
              <table className={v.table}>
                <thead>
                  <tr>
                    <th>Date (UTC)</th>
                    <th className={v.num}>Detections</th>
                    <th className={v.num}>Night</th>
                    <th className={v.num}>Max FRP</th>
                    <th className={v.num}>Mean FRP</th>
                    <th>Satellites</th>
                  </tr>
                </thead>
                <tbody>
                  {daily
                    .slice()
                    .reverse()
                    .map((d) => (
                      <tr key={d.day}>
                        <td className="mono">{d.day}</td>
                        <td className={`${v.num} mono`}>{d.detections}</td>
                        <td className={`${v.num} mono`}>{d.night}</td>
                        <td className={`${v.num} mono`}>{fmtNum(d.max_frp)}</td>
                        <td className={`${v.num} mono`}>{fmtNum(d.mean_frp)}</td>
                        <td className={s.muted}>{(d.satellites || []).filter(Boolean).join(', ')}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        <div className={s.grid2}>
          <Card
            title="Classification rationale"
            aside={
              cls.classifier && (
                <span className={s.muted}>
                  {cls.classifier.name} · {cls.classifier.kind} · not a trained model
                </span>
              )
            }
          >
            <ul className={v.bullets}>
              {cls.rationale.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            {cls.alternatives_rejected?.length > 0 && (
              <>
                <h3 className={v.subhead}>Alternatives considered and rejected</h3>
                <ul className={`${v.bullets} ${v.rejected}`}>
                  {cls.alternatives_rejected.map((a) => (
                    <li key={a.class}>
                      <b>{a.label}</b> — {a.reason.replace(/^Not selected: /, '')}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {intel.evidence?.length > 0 && (
              <>
                <h3 className={v.subhead}>Evidence</h3>
                <ul className={v.bullets}>
                  {intel.evidence.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </>
            )}
            {intel.caveats?.length > 0 && (
              <ul className={`${v.bullets} ${v.caveats}`}>
                {intel.caveats.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            )}
          </Card>
          <Card
            title="Intelligence factors"
            aside={
              <span className={s.muted}>
                {intel.engine_version} · analysed {fmtRelative(intel.analyzed_at)}
              </span>
            }
          >
            {intel.factors?.length ? (
              <Factors factors={intel.factors} />
            ) : (
              <div className={s.muted}>No factor breakdown stored for this event.</div>
            )}
          </Card>
        </div>

        <div className={s.grid2}>
          <Card title="Alert history" aside={<span className={s.muted}>{alerts.length} alert(s)</span>}>
            {alerts.length === 0 ? (
              <EmptyState icon={BellRing} title="No alert raised">
                No alert rule fired at or above the minimum alert severity for this incident.
              </EmptyState>
            ) : (
              <ul className={v.alerts}>
                {alerts.map((a) => (
                  <li key={a.id} className={v.alert} style={{ '--bar': PRIORITY[a.severity]?.color }}>
                    <div className={v.alertTop}>
                      <PriorityBadge priority={a.severity} />
                      <Badge tone={ALERT_TONE[a.status]} variant="outline">
                        {titleCase(a.status)}
                      </Badge>
                      <span className={s.muted}>#{a.id}</span>
                      <span className={`${v.alertTime} ${s.muted}`}>
                        raised {fmtUtc(a.created_at)}
                        {a.escalation_count ? ` · escalated ${a.escalation_count}×` : ''}
                      </span>
                    </div>
                    <div className={v.alertDesc}>{a.description}</div>
                    <div className={v.rules}>
                      {(a.rules || []).map((r) => (
                        <span key={r} className={v.rule}>
                          {RULE_LABELS[r] || r}
                        </span>
                      ))}
                    </div>
                    {a.resolution && <div className={s.muted}>Resolution: {a.resolution}</div>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Timeline">
            <Timeline events={timeline} />
          </Card>
        </div>

        <div className={s.grid2}>
          <Card title="Satellite coverage">
            <table className={v.table}>
              <thead>
                <tr>
                  <th>Satellite</th>
                  <th>Product</th>
                  <th className={v.num}>Detections</th>
                  <th className={v.num}>High conf.</th>
                  <th className={v.num}>Max FRP</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {satellites.map((sat) => (
                  <tr key={`${sat.satellite_name}-${sat.product}`}>
                    <td>{sat.satellite_name}</td>
                    <td className="mono">{sat.product}</td>
                    <td className={`${v.num} mono`}>{sat.detections}</td>
                    <td className={`${v.num} mono`}>{sat.high_confidence}</td>
                    <td className={`${v.num} mono`}>{fmtNum(sat.max_frp)}</td>
                    <td title={fmtUtc(sat.last_seen)}>{fmtRelative(sat.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="Land-cover context">
            <LandCover cluster={{ ...cluster, land_cover_fractions: data.land_cover.fractions }} classes={classes.data} />
          </Card>
        </div>

        <Card
          title="Detections"
          aside={<span className={s.muted}>{fmtInt(observations.length)} satellite detections</span>}
          className={v.full}
        >
          <div className={v.scrollTable} style={{ maxHeight: 420 }}>
            <table className={v.table}>
              <thead>
                <tr>
                  <th>Acquired (UTC)</th>
                  <th>Satellite</th>
                  <th>Product</th>
                  <th>Location</th>
                  <th className={v.num}>FRP (MW)</th>
                  <th className={v.num}>Brightness (K)</th>
                  <th>Confidence</th>
                  <th>Day/night</th>
                </tr>
              </thead>
              <tbody>
                {observations.slice(0, obsShown).map((o) => (
                  <tr key={o.id}>
                    <td className="mono">{fmtUtc(o.acquired_at).replace(' UTC', '')}</td>
                    <td>{o.satellite_name}</td>
                    <td className="mono">{o.product}</td>
                    <td className="mono">{fmtCoord(o.latitude, o.longitude, 4)}</td>
                    <td className={`${v.num} mono`}>{fmtNum(o.frp)}</td>
                    <td className={`${v.num} mono`}>{fmtNum(o.brightness, 1)}</td>
                    <td>{o.confidence_pct != null ? `${o.confidence_pct}%` : titleCase(o.confidence_level || '—')}</td>
                    <td>{o.daynight === 'N' ? 'Night' : o.daynight === 'D' ? 'Day' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {observations.length > obsShown && (
            <div className={v.more}>
              <Button size="sm" onClick={() => setObsShown(obsShown + OBS_PAGE)}>
                Show more ({fmtInt(observations.length - obsShown)} remaining)
              </Button>
            </div>
          )}
        </Card>

        <Card title="Data provenance" className={v.full}>
          <dl className={v.prov}>
            <dt>Thermal detections</dt>
            <dd>
              {provenance.thermal.source} · products {provenance.thermal.products.join(', ') || '—'} · ingested by{' '}
              {provenance.thermal.ingestion_runs.length} run(s)
              {provenance.thermal.ingestion_runs.length > 0 && ` (latest ${fmtUtc(provenance.thermal.ingestion_runs.at(-1).started_at)})`}
            </dd>
            <dt>Facility</dt>
            <dd>
              {provenance.facility ? (
                <>
                  {provenance.facility.source} ·{' '}
                  <a href={provenance.facility.url} target="_blank" rel="noreferrer" className={v.link}>
                    {provenance.facility.element}
                  </a>{' '}
                  · snapshot {fmtUtc(provenance.facility.snapshot)}
                </>
              ) : (
                'No associated facility'
              )}
            </dd>
            <dt>Land cover</dt>
            <dd>
              {provenance.land_cover
                ? `${provenance.land_cover.source} · tile ${provenance.land_cover.tile} · sampled ${fmtUtc(provenance.land_cover.sampled_at)}`
                : 'Not sampled'}
            </dd>
            <dt>Boundary</dt>
            <dd>{provenance.boundary || '—'}</dd>
            <dt>Analysis</dt>
            <dd>
              {provenance.analysis.engine} · classifier {provenance.analysis.classifier?.name} ({provenance.analysis.classifier?.kind}) ·
              analysed {fmtUtc(provenance.analysis.analyzed_at)}
            </dd>
          </dl>
          <p className={v.disclaimer}>
            Classifications are inferred from satellite thermal detections and open data by transparent rules. They indicate likely heat
            sources and require on-the-ground verification before any enforcement action.
          </p>
        </Card>
      </div>
    </div>
  );
}
