import { useEffect } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import TopBar from './components/layout/TopBar.jsx';
import ModeBanner from './components/layout/ModeBanner.jsx';
import Sidebar from './components/layout/Sidebar.jsx';
import Toasts from './components/layout/Toasts.jsx';
import DashboardView from './views/DashboardView.jsx';
import IncidentsView from './views/IncidentsView.jsx';
import AlertsView from './views/AlertsView.jsx';
import FacilitiesView from './views/FacilitiesView.jsx';
import ThermalSourcesView from './views/ThermalSourcesView.jsx';
import InvestigationView from './views/InvestigationView.jsx';
import AnalyticsView from './views/AnalyticsView.jsx';
import SettingsView from './views/SettingsView.jsx';
import NotFoundView from './views/NotFoundView.jsx';
import { useApp } from './state/AppContext.jsx';
import s from './App.module.css';

const LEGACY_HASH = { monitor: '/dashboard', incidents: '/incidents', alerts: '/alerts', facilities: '/facilities', sources: '/settings' };

/** Gives non-component code (live notifications) a way to navigate, and upgrades old #/ links. */
function NavigationBridge() {
  const navigate = useNavigate();
  const location = useLocation();
  const { navigateRef } = useApp();
  useEffect(() => {
    navigateRef.current = navigate;
  }, [navigate, navigateRef]);
  useEffect(() => {
    const legacy = location.hash.replace('#/', '');
    if (LEGACY_HASH[legacy]) navigate(LEGACY_HASH[legacy], { replace: true });
  }, [location.hash, navigate]);
  return null;
}

export default function App() {
  return (
    <div className={s.shell}>
      <NavigationBridge />
      <TopBar />
      <Sidebar />
      <main className={s.main} id="main">
        <ModeBanner />
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardView />} />
          <Route path="/incidents" element={<IncidentsView />} />
          <Route path="/alerts" element={<AlertsView />} />
          <Route path="/facilities" element={<FacilitiesView />} />
          <Route path="/thermal-sources" element={<ThermalSourcesView />} />
          <Route path="/investigation/:id" element={<InvestigationView />} />
          <Route path="/analytics" element={<AnalyticsView />} />
          <Route path="/settings" element={<SettingsView />} />
          <Route path="*" element={<NotFoundView />} />
        </Routes>
      </main>
      <Toasts />
    </div>
  );
}
