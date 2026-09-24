import FilterBar from '../components/common/FilterBar.jsx';
import ThermalMap from '../components/map/ThermalMap.jsx';
import KpiStrip from '../components/panels/KpiStrip.jsx';
import RightRail from '../components/panels/RightRail.jsx';
import SourceHealthStrip from '../components/panels/SourceHealthStrip.jsx';
import { useQueryFilters } from '../hooks/useQueryFilters.js';
import s from './MonitorView.module.css';

export default function DashboardView() {
  useQueryFilters();
  return (
    <div className={s.grid}>
      <div className={s.filters}>
        <FilterBar />
      </div>
      <div className={s.kpis}>
        <KpiStrip />
      </div>
      <div className={s.map}>
        <ThermalMap />
      </div>
      <div className={s.health}>
        <SourceHealthStrip />
      </div>
      <aside className={s.rail} aria-label="Thermal events, incidents and alerts">
        <RightRail />
      </aside>
    </div>
  );
}
