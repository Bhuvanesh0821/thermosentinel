import { NavLink } from 'react-router-dom';
import { BarChart3, Bell, Factory, FileCode2, Flame, Radar, Settings, Siren } from 'lucide-react';
import { docsUrl } from '../../api/client.js';
import { useApi } from '../../hooks/useApi.js';
import s from './Sidebar.module.css';

const ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: Radar },
  { to: '/incidents', label: 'Incidents', icon: Siren },
  { to: '/alerts', label: 'Alerts', icon: Bell, badge: 'alerts' },
  { to: '/thermal-sources', label: 'Sources', title: 'Persistent thermal sources', icon: Flame },
  { to: '/facilities', label: 'Facilities', icon: Factory },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
];

export default function Sidebar() {
  const alerts = useApi('/api/alerts', { status: 'open', limit: 1 });
  const openAlerts = alerts.meta?.total || 0;
  return (
    <nav className={s.nav} aria-label="Primary">
      <ul className={s.list}>
        {ITEMS.map(({ to, label, title, icon: Icon, badge }) => (
          <li key={to}>
            <NavLink to={to} className={s.item} title={title || label}>
              <Icon size={19} strokeWidth={1.8} />
              <span className={s.label}>{label}</span>
              {badge === 'alerts' && openAlerts > 0 && (
                <span className={s.badge} aria-label={`${openAlerts} open alerts`}>
                  {openAlerts > 99 ? '99+' : openAlerts}
                </span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className={s.bottom}>
        <NavLink to="/settings" className={s.item} title="Settings & system health">
          <Settings size={19} strokeWidth={1.8} />
          <span className={s.label}>Settings</span>
        </NavLink>
        <a className={`${s.item} ${s.desktopOnly}`} href={docsUrl()} target="_blank" rel="noreferrer" title="API documentation (OpenAPI)">
          <FileCode2 size={19} strokeWidth={1.8} />
          <span className={s.label}>API</span>
        </a>
      </div>
    </nav>
  );
}
