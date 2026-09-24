import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BellRing, Check, CheckCheck, ChevronDown, ExternalLink } from 'lucide-react';
import { api } from '../../api/client.js';
import { useApp } from '../../state/AppContext.jsx';
import { PRIORITY } from '../../utils/constants.js';
import { fmtRelative, fmtUtc } from '../../utils/format.js';
import { Button, EmptyState, ErrorState, SkeletonRows } from '../common/ui.jsx';
import s from './NotificationCenter.module.css';

const EVENT_LABEL = (event) => (String(event).startsWith('escalated') ? 'Escalated' : 'New alert');

export default function NotificationCenter({ state, onClose }) {
  const navigate = useNavigate();
  const { pushToast, browserNotify, setBrowserNotify } = useApp();
  const { data, meta, error, loading, reload } = state;
  const [expanded, setExpanded] = useState(null);
  const permission = typeof Notification !== 'undefined' ? Notification.permission : 'unsupported';

  async function markAll() {
    try {
      await api.post('/api/notifications/read-all');
      reload();
    } catch (e) {
      pushToast({ tone: 'error', title: 'Could not update notifications', body: e.message });
    }
  }
  async function markRead(note) {
    if (note.read_at) return;
    try {
      await api.post(`/api/notifications/${note.id}/read`);
      reload();
    } catch {
      /* non-critical */
    }
  }
  function open(note) {
    markRead(note);
    navigate(note.incident_id ? `/investigation/${note.incident_id}` : '/alerts');
    onClose();
  }
  async function enableBrowser() {
    if (permission === 'unsupported') return;
    const result = permission === 'granted' ? 'granted' : await Notification.requestPermission();
    setBrowserNotify(result === 'granted');
    if (result !== 'granted') pushToast({ tone: 'info', title: 'Browser notifications blocked', body: 'Allow notifications for this site in your browser settings.' });
  }

  return (
    <div className={s.pop} role="dialog" aria-label="Notifications">
      <header className={s.head}>
        <span className={s.title}>
          Notifications {meta?.unread ? <span className={s.unread}>{meta.unread} unread</span> : null}
        </span>
        <Button size="sm" variant="ghost" icon={CheckCheck} onClick={markAll} disabled={!meta?.unread}>
          Mark all read
        </Button>
      </header>
      {permission !== 'unsupported' && !(browserNotify && permission === 'granted') && (
        <button type="button" className={s.browserPrompt} onClick={enableBrowser}>
          <BellRing size={14} /> Enable browser notifications for new and escalated alerts
        </button>
      )}
      <div className={s.list}>
        {loading && <SkeletonRows rows={3} height={48} />}
        {error && <ErrorState error={error} onRetry={reload} compact />}
        {!loading && !error && data?.length === 0 && (
          <EmptyState title="No notifications">Alerts raised by the alert engine from real detections appear here.</EmptyState>
        )}
        {data?.map((note) => (
          <div key={note.id} className={s.item} data-unread={!note.read_at}>
            <span className={s.sev} style={{ background: PRIORITY[note.severity]?.color || 'var(--idle)' }} title={`${note.severity} severity`} />
            <div className={s.body}>
              <div className={s.meta}>
                <span className={s.event}>{EVENT_LABEL(note.event)}</span>
                <span className={s.severity}>{PRIORITY[note.severity]?.label || note.severity}</span>
                <span className={s.time} title={fmtUtc(note.created_at)}>
                  {fmtRelative(note.created_at)}
                </span>
              </div>
              <button type="button" className={s.itemTitle} onClick={() => open(note)}>
                {note.title}
              </button>
              {expanded === note.id && <p className={s.itemText}>{note.body}</p>}
              <div className={s.actions}>
                <button type="button" className={s.link} onClick={() => setExpanded(expanded === note.id ? null : note.id)}>
                  <ChevronDown size={12} style={{ transform: expanded === note.id ? 'rotate(180deg)' : 'none' }} /> Details
                </button>
                <button type="button" className={s.link} onClick={() => open(note)}>
                  <ExternalLink size={12} /> Investigate
                </button>
                {!note.read_at && (
                  <button type="button" className={s.link} onClick={() => markRead(note)}>
                    <Check size={12} /> Mark read
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      <footer className={s.foot}>
        <button
          type="button"
          className={s.link}
          onClick={() => {
            navigate('/alerts');
            onClose();
          }}
        >
          Open alert centre →
        </button>
      </footer>
    </div>
  );
}
