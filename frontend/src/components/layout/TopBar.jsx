import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, Loader2 } from 'lucide-react';
import { useApi } from '../../hooks/useApi.js';
import { useApp } from '../../state/AppContext.jsx';
import { fmtRelative, fmtUtc } from '../../utils/format.js';
import { Dot } from '../common/ui.jsx';
import GlobalSearch from './GlobalSearch.jsx';
import NotificationCenter from './NotificationCenter.jsx';
import VoiceControl from './VoiceControl.jsx';
import s from './TopBar.module.css';

function BrandMark() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#0D1726" />
      <circle cx="16" cy="16" r="9" fill="none" stroke="#5B7FD6" strokeWidth="1.6" />
      <circle cx="16" cy="16" r="4.6" fill="none" stroke="#9FB4E8" strokeWidth="1.4" />
      <circle cx="16" cy="16" r="2" fill="#F97316" />
      <path d="M16 3.5v4M16 24.5v4M3.5 16h4M24.5 16h4" stroke="#5B7FD6" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function LiveStatus() {
  const { stream, pipeline } = useApp();
  const health = useApi('/api/health', null, { interval: 60000 });
  const summary = useApi('/api/stats/summary', { hours: 24 }, { interval: 120000 });
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 30000);
    return () => clearInterval(id);
  }, []);

  const apiDown = health.error?.code === 'network_error';
  const db = health.data?.database?.status;
  const running = pipeline.running || health.data?.pipeline?.running;
  const latest = summary.data?.detections?.latest_acquisition;

  let tone = 'ok';
  let label = 'Live';
  if (apiDown) {
    tone = 'err';
    label = 'API offline';
  } else if (db && db !== 'connected') {
    tone = 'warn';
    label = db === 'not_configured' ? 'Database not configured' : 'Database unavailable';
  } else if (stream.status !== 'live') {
    tone = 'warn';
    label = stream.status === 'connecting' ? 'Connecting' : 'Stream reconnecting';
  }
  return (
    <div className={s.status} role="status" aria-live="polite">
      <span className={s.statusMain} title={stream.transport ? `Real-time transport: ${stream.transport === 'websocket' ? 'WebSocket' : 'Server-Sent Events'}` : undefined}>
        <Dot tone={tone} pulse={tone === 'ok'} />
        <span className={s.statusLabel}>{label}</span>
      </span>
      {running && (
        <span className={s.statusChip}>
          <Loader2 size={12} className={s.spin} /> Pipeline{pipeline.progress ? ` · ${pipeline.progress}` : ' running'}
        </span>
      )}
      {latest && !apiDown && (
        <span className={s.statusMeta} title={`Latest satellite acquisition: ${fmtUtc(latest)}`}>
          Latest acquisition <b className="mono">{fmtRelative(latest)}</b>
        </span>
      )}
    </div>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const notes = useApi('/api/notifications', { limit: 25 }, { interval: 60000 });
  const unread = notes.meta?.unread || 0;
  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);
  return (
    <div className={s.popWrap} ref={ref}>
      <button type="button" className={s.iconAction} aria-label={`Notifications${unread ? ` (${unread} unread)` : ''}`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Bell size={17} />
        {unread > 0 && <span className={s.count}>{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && <NotificationCenter state={notes} onClose={() => setOpen(false)} />}
    </div>
  );
}

export default function TopBar() {
  const config = useApi('/api/map/config', null, { live: false });
  const region = config.data?.region;
  return (
    <header className={s.bar}>
      <Link to="/dashboard" className={s.brand} aria-label="ThermoSentinel dashboard">
        <BrandMark />
        <div className={s.brandText}>
          <span className={s.brandName}>ThermoSentinel</span>
          <span className={s.brandSub}>Industrial Thermal Intelligence</span>
        </div>
      </Link>
      {region && (
        <div className={s.region} title={`Monitoring area: ${region.boundary?.monitoring_area || region.name}`}>
          <span className={s.regionLabel}>Region</span>
          <span className={s.regionName}>{region.name}</span>
        </div>
      )}
      <GlobalSearch />
      <LiveStatus />
      <div className={s.actions}>
        <VoiceControl />
        <Notifications />
        <div className={s.divider} />
        <div className={s.profile} title="Authentication is planned for Stage 3">
          <span className={s.avatar}>OP</span>
          <span className={s.profileText}>
            <span className={s.profileName}>Operator</span>
            <span className={s.profileRole}>Local session</span>
          </span>
        </div>
      </div>
    </header>
  );
}
