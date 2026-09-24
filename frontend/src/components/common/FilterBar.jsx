import { RotateCcw } from 'lucide-react';
import { DEFAULT_FILTERS, useApp } from '../../state/AppContext.jsx';
import { CLASSIFICATION, PRIORITY_ORDER, PRIORITY, WINDOW_OPTIONS } from '../../utils/constants.js';
import MultiSelect from './MultiSelect.jsx';
import { Segmented, Select } from './ui.jsx';
import s from './FilterBar.module.css';

const FACILITY_OPTIONS = [
  ['gas_flare', 'Gas flare stack'],
  ['refinery', 'Oil refinery'],
  ['petrochemical', 'Petrochemical complex'],
  ['oil_gas_facility', 'Oil & gas facility'],
  ['lng_terminal', 'LNG facility'],
  ['thermal_power_plant', 'Thermal power plant'],
  ['steel_plant', 'Iron & steel plant'],
  ['metal_smelter', 'Metal smelter / foundry'],
  ['cement_plant', 'Cement plant'],
  ['brick_kiln', 'Brick kiln / kiln'],
  ['mining', 'Mining area'],
  ['chemical_plant', 'Chemical / fertiliser plant'],
  ['industrial_works', 'Industrial works'],
].map(([value, label]) => ({ value, label }));

const PERSISTENCE_OPTIONS = [
  { value: 'persistent', label: 'Persistent' },
  { value: 'recurring', label: 'Recurring' },
  { value: 'transient', label: 'Transient' },
  { value: 'insufficient_history', label: 'Insufficient history' },
];

/**
 * One filter row above the content it scopes (map + panels). `fields` limits which controls show.
 */
export default function FilterBar({
  fields = ['hours', 'severity', 'event', 'facility', 'persistence', 'confidence', 'area'],
  windows = WINDOW_OPTIONS,
  trailing,
}) {
  const { filters, setFilters } = useApp();
  const set = (key) => (value) => setFilters((f) => ({ ...f, [key]: value }));
  const has = (k) => fields.includes(k);
  const dirty = fields.some((k) => {
    const map = {
      hours: 'hours',
      severity: 'minPriority',
      event: 'classification',
      facility: 'facilityType',
      persistence: 'persistence',
      confidence: 'confidence',
      area: 'area',
    };
    return JSON.stringify(filters[map[k]]) !== JSON.stringify(DEFAULT_FILTERS[map[k]]);
  });

  return (
    <div className={s.bar} role="toolbar" aria-label="Filters">
      {has('hours') && <Segmented options={windows} value={filters.hours} onChange={set('hours')} label="Time window" />}
      {has('severity') && (
        <Select
          label="Minimum severity"
          value={filters.minPriority}
          onChange={set('minPriority')}
          options={[
            { value: null, label: 'Any severity' },
            ...PRIORITY_ORDER.slice()
              .reverse()
              .map((p) => ({ value: p, label: `${PRIORITY[p].label}${p === 'critical' ? '' : ' +'}` })),
          ]}
        />
      )}
      {has('event') && (
        <MultiSelect
          label="Event type"
          swatch
          value={filters.classification}
          onChange={set('classification')}
          options={Object.entries(CLASSIFICATION).map(([value, c]) => ({ value, label: c.label, color: c.color }))}
        />
      )}
      {has('facility') && (
        <MultiSelect label="Facility" value={filters.facilityType} onChange={set('facilityType')} options={FACILITY_OPTIONS} />
      )}
      {has('persistence') && (
        <MultiSelect label="Persistence" value={filters.persistence} onChange={set('persistence')} options={PERSISTENCE_OPTIONS} />
      )}
      {has('confidence') && (
        <Select
          label="Minimum detection confidence"
          value={filters.confidence}
          onChange={set('confidence')}
          options={[
            { value: null, label: 'Any confidence' },
            { value: 'nominal', label: 'Nominal +' },
            { value: 'high', label: 'High' },
          ]}
        />
      )}
      {has('area') && (
        <Segmented
          label="Geographic area"
          options={[
            { value: 'india', label: 'All India' },
            { value: 'view', label: 'Map view' },
            ...(filters.area === 'place' && filters.placeName ? [{ value: 'place', label: filters.placeName }] : []),
          ]}
          value={filters.area}
          onChange={(v) => setFilters((f) => ({ ...f, area: v, ...(v === 'place' ? {} : { placeBbox: null, placeName: null }) }))}
        />
      )}
      {dirty && (
        <button
          type="button"
          className={s.reset}
          onClick={() =>
            setFilters((f) => ({
              ...f,
              ...Object.fromEntries(Object.entries(DEFAULT_FILTERS).filter(([k]) => !['minFrp', 'instrument'].includes(k))),
            }))
          }
          title="Reset filters"
        >
          <RotateCcw size={13} /> Reset
        </button>
      )}
      {trailing && <div className={s.trailing}>{trailing}</div>}
    </div>
  );
}
