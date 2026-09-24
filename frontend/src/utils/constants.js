// Visual encodings shared by the map, legend and panels.

// Priority is an ordered severity scale: one warm hue stepping light -> dark (validated with the
// dataviz ordinal checks). Identity never relies on colour alone: badges carry the word, map
// markers also scale in size.
export const PRIORITY = {
  critical: { label: 'Critical', color: '#701a08', soft: '#f6e3dc' },
  high: { label: 'High', color: '#ad3a16', soft: '#f9e7de' },
  medium: { label: 'Medium', color: '#d9683a', soft: '#fcefe7' },
  low: { label: 'Low', color: '#eaa07c', soft: '#fdf5ef' },
};

export const PRIORITY_ORDER = ['critical', 'high', 'medium', 'low'];

// FRP (MW) stops for the thermal detection colour ramp.
export const FRP_STOPS = [
  [0, '#FCD34D'],
  [5, '#FB923C'],
  [20, '#EA580C'],
  [60, '#DC2626'],
  [150, '#7F1D1D'],
];

// Facility identity on the map. Three cool hues (validated all-pairs for colour-vision
// deficiency with the dataviz palette checks; warm hues are reserved for heat) + gray "other".
// Exact facility types are always named in the legend, popups and the Facilities table.
export const FACILITY_GROUPS = {
  hydrocarbon: {
    label: 'Oil, gas & flaring',
    color: '#4a3aa7',
    types: ['gas_flare', 'refinery', 'petrochemical', 'oil_gas_facility', 'lng_terminal'],
  },
  power: { label: 'Thermal power', color: '#2a78d6', types: ['thermal_power_plant'] },
  heavy: {
    label: 'Metals, cement, kilns & mining',
    color: '#1baf7a',
    types: ['steel_plant', 'metal_smelter', 'cement_plant', 'brick_kiln', 'mining'],
  },
  other: { label: 'Chemical & other industry', color: '#7a8697', types: ['chemical_plant', 'industrial_works'] },
};

export function facilityColor(type) {
  const group = Object.values(FACILITY_GROUPS).find((g) => g.types.includes(type));
  return group ? group.color : FACILITY_GROUPS.other.color;
}

// Event classes (rule-based classifier ts-rules 2.0). Swatches sit beside the text label; the
// label always carries the identity.
export const CLASSIFICATION = {
  gas_flare_like: { label: 'Gas-flare-like activity', short: 'Gas-flare-like', color: '#4a3aa7' },
  mining_associated: { label: 'Mining-associated thermal activity', short: 'Mining-associated', color: '#1baf7a' },
  persistent_industrial_source: { label: 'Persistent industrial thermal source', short: 'Persistent industrial', color: '#2a78d6' },
  industrial_associated_event: { label: 'Industrial-associated thermal event', short: 'Industrial-associated', color: '#6da7ec' },
  persistent_unattributed_source: { label: 'Persistent thermal source (no mapped facility)', short: 'Unmapped source', color: '#e87ba4' },
  agricultural_burning: { label: 'Possible agricultural burning', short: 'Agricultural?', color: '#eda100' },
  vegetation_fire: { label: 'Possible wildfire / vegetation fire', short: 'Vegetation fire?', color: '#008300' },
  unclassified_anomaly: { label: 'Unclassified thermal anomaly', short: 'Unclassified', color: '#97a1af' },
};

export const INDUSTRIAL_CLASSES = ['gas_flare_like', 'mining_associated', 'persistent_industrial_source', 'industrial_associated_event'];

export const PERSISTENCE = {
  persistent: { label: 'Persistent', tone: 'critical' },
  recurring: { label: 'Recurring', tone: 'high' },
  transient: { label: 'Transient', tone: 'low' },
  insufficient_history: { label: 'Insufficient history', tone: 'idle' },
};

export const RELATIONSHIP = {
  inside_footprint: 'Inside facility footprint',
  adjacent: 'Adjacent (≤ 1 km)',
  nearby: 'Nearby (≤ 3 km)',
  distant: 'Distant',
  none: 'No facility in range',
};

export const STATUS_TONE = {
  connected: 'ok',
  degraded: 'warn',
  unavailable: 'err',
  not_configured: 'idle',
  disabled: 'idle',
  unknown: 'idle',
};

export const WINDOW_OPTIONS = [
  { value: 24, label: '24 h' },
  { value: 48, label: '48 h' },
  { value: 168, label: '7 d' },
  { value: 720, label: '30 d' },
];
