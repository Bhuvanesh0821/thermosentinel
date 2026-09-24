import { useApp } from '../../state/AppContext.jsx';
import { Select } from '../common/ui.jsx';
import s from './Map.module.css';

// Detection-level quick filters (shared event filters live in the filter bar above the map).
const FRP_OPTIONS = [
  { value: null, label: 'Any FRP' },
  { value: '5', label: 'FRP ≥ 5' },
  { value: '10', label: 'FRP ≥ 10' },
  { value: '25', label: 'FRP ≥ 25' },
  { value: '50', label: 'FRP ≥ 50' },
  { value: '100', label: 'FRP ≥ 100' },
];
const SENSOR_OPTIONS = [
  { value: null, label: 'All sensors' },
  { value: 'VIIRS', label: 'VIIRS' },
  { value: 'MODIS', label: 'MODIS' },
];
const DN_OPTIONS = [
  { value: null, label: 'Day & night' },
  { value: 'D', label: 'Day' },
  { value: 'N', label: 'Night' },
];

export default function MapFilters() {
  const { filters, setFilters } = useApp();
  const set = (key) => (value) => setFilters((f) => ({ ...f, [key]: value }));
  return (
    <div className={`${s.floating} ${s.filters}`} role="toolbar" aria-label="Detection filters">
      <span className={s.filtersLabel}>Detections</span>
      <Select label="Minimum fire radiative power (MW)" value={filters.minFrp} onChange={set('minFrp')} options={FRP_OPTIONS} />
      <Select label="Sensor" value={filters.instrument} onChange={set('instrument')} options={SENSOR_OPTIONS} />
      <Select label="Day or night" value={filters.daynight} onChange={set('daynight')} options={DN_OPTIONS} />
    </div>
  );
}
