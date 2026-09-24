import { useState } from 'react';
import { useApi } from '../../hooks/useApi.js';
import { useApp } from '../../state/AppContext.jsx';
import { fmtInt } from '../../utils/format.js';
import ClusterDetail from './ClusterDetail.jsx';
import EventList from './EventList.jsx';
import IncidentList from './IncidentList.jsx';
import AlertList from './AlertList.jsx';
import s from './RightRail.module.css';

const TABS = [
  { id: 'events', label: 'Thermal events' },
  { id: 'incidents', label: 'Incidents' },
  { id: 'alerts', label: 'Alerts' },
];

export default function RightRail() {
  const { selection, setSelection } = useApp();
  const [tab, setTab] = useState('events');
  const incidentCount = useApi('/api/incidents', { status: 'active,monitoring', limit: 1 });
  const alertCount = useApi('/api/alerts', { status: 'open', limit: 1 });
  const counts = { incidents: incidentCount.meta?.total, alerts: alertCount.meta?.total };

  if (selection?.type === 'cluster') {
    return (
      <div className={s.rail}>
        <ClusterDetail clusterId={selection.id} incidentId={selection.incidentId} onBack={() => setSelection(null)} />
      </div>
    );
  }

  return (
    <div className={s.rail}>
      <div className={s.tabs} role="tablist" aria-label="Operational lists">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className={s.tab} onClick={() => setTab(t.id)}>
            {t.label}
            {counts[t.id] > 0 && <span className={s.tabCount}>{fmtInt(counts[t.id])}</span>}
          </button>
        ))}
      </div>
      <div className={s.body} role="tabpanel">
        {tab === 'events' && <EventList />}
        {tab === 'incidents' && <IncidentList compact />}
        {tab === 'alerts' && <AlertList compact />}
      </div>
    </div>
  );
}
