// MapLibre style + layer definitions. Every data layer is fed from the ThermoSentinel API.
import { FACILITY_GROUPS, FRP_STOPS, PRIORITY } from '../../utils/constants.js';

export const EMPTY_FC = { type: 'FeatureCollection', features: [] };

export const DATA_SOURCES = ['boundary', 'riskzones', 'footprints', 'landcover', 'facilities', 'clusters', 'hotspots', 'incidents', 'selection'];

// Facilities are generalised into count clusters below this zoom: ~7,000 points (mostly brick
// kilns) would otherwise be drawn at once at national scale.
export const FACILITY_CLUSTER_MAX_ZOOM = 7;
export const SOURCE_OPTIONS = {
  facilities: { cluster: true, clusterMaxZoom: FACILITY_CLUSTER_MAX_ZOOM, clusterRadius: 36 },
};

// India only: everything outside the monitoring area (official-claim boundary + EEZ) is masked.
export function boundaryLayers() {
  return [
    {
      id: 'boundary-mask',
      type: 'fill',
      source: 'boundary',
      filter: ['==', ['get', 'role'], 'mask'],
      // Veil over everything outside India; recoloured per basemap by applyBasemap().
      paint: { 'fill-color': '#E8ECF1', 'fill-opacity': 0.72 },
    },
    {
      id: 'boundary-eez',
      type: 'line',
      source: 'boundary',
      filter: ['==', ['get', 'role'], 'monitoring_area'],
      paint: { 'line-color': '#5B7FD6', 'line-width': 1, 'line-dasharray': [3, 2], 'line-opacity': 0.8 },
    },
    {
      id: 'boundary-land',
      type: 'line',
      source: 'boundary',
      filter: ['==', ['get', 'role'], 'land'],
      paint: { 'line-color': '#1F2A3D', 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 1, 8, 1.8], 'line-opacity': 0.9 },
    },
  ];
}

const priorityColor = [
  'match',
  ['get', 'priority'],
  'critical',
  PRIORITY.critical.color,
  'high',
  PRIORITY.high.color,
  'medium',
  PRIORITY.medium.color,
  'low',
  PRIORITY.low.color,
  '#64748B',
];

// Secondary encoding for priority on the map: size grows with severity, so it is never colour alone.
const priorityScale = ['match', ['get', 'priority'], 'critical', 1.35, 'high', 1.15, 'medium', 1, 0.85];

const facilityColor = ['match', ['get', 'type']];
Object.values(FACILITY_GROUPS).forEach((group) => {
  facilityColor.push(group.types, group.color);
});
facilityColor.push(FACILITY_GROUPS.other.color);

const frpColor = ['interpolate', ['linear'], ['coalesce', ['get', 'frp'], 0], ...FRP_STOPS.flat()];

const clusterRadius = (scale) => [
  'interpolate',
  ['linear'],
  ['get', 'observation_count'],
  1,
  7 * scale,
  5,
  10 * scale,
  20,
  15 * scale,
  100,
  24 * scale,
];

// Minimal style used only if the vector basemap style cannot be fetched.
export const FALLBACK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#EEF1F5' } }],
};

export async function loadBaseStyle(url) {
  if (!url) return { style: FALLBACK_STYLE, ok: false };
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return { style: await response.json(), ok: true };
  } catch {
    return { style: FALLBACK_STYLE, ok: false };
  }
}

/** Hide every boundary line of the basemap: only India's official boundary is drawn. */
export function hideBasemapBoundaries(map) {
  map.getStyle().layers.forEach((layer) => {
    if (layer['source-layer'] === 'boundary' || layer.id.startsWith('boundary') || layer.type === 'fill-extrusion') {
      map.setLayoutProperty(layer.id, 'visibility', 'none');
    }
  });
}

/** First label layer (road arrows / shields excluded): our boundary and data sit below place names. */
export function firstSymbolLayer(map) {
  const layers = map.getStyle().layers;
  return (
    layers.find((l) => l.type === 'symbol' && l['source-layer'] !== 'transportation' && l['source-layer'] !== 'transportation_name')?.id ||
    layers.find((l) => l.type === 'symbol')?.id
  );
}

/** First road layer: imagery goes below it, so a satellite view keeps roads and labels (hybrid). */
function firstRoadLayer(map) {
  return map.getStyle().layers.find((l) => l['source-layer'] === 'transportation')?.id;
}

/** Keep place names (cities, states, countries, seas) readable above the data layers, as in Google Maps. */
export function raisePlaceLabels(map) {
  map.getStyle().layers.forEach((l) => {
    if (l.type === 'symbol' && (l['source-layer'] === 'place' || l['source-layer'] === 'water_name')) map.moveLayer(l.id);
  });
}

/** Raster basemaps (satellite, VIIRS) sit above the vector land/water fills, below roads and labels. */
export function addRasterBasemaps(map, basemaps, beforeId) {
  const anchor = firstRoadLayer(map) || beforeId;
  basemaps
    .filter((b) => b.tiles)
    .forEach((b) => {
      map.addSource(`bm-${b.id}`, {
        type: 'raster',
        tiles: b.tiles,
        tileSize: b.tile_size,
        maxzoom: b.max_zoom,
        attribution: b.attribution,
      });
      map.addLayer({ id: `bm-${b.id}`, type: 'raster', source: `bm-${b.id}`, layout: { visibility: 'none' } }, anchor);
    });
}

// Paint used for the vector basemap when it is drawn over imagery (Google-style hybrid).
const HYBRID_LABEL = { 'text-color': '#FFFFFF', 'text-halo-color': 'rgba(0, 0, 0, 0.78)', 'text-halo-width': 1.4 };
const HYBRID_MASK = { 'fill-color': '#0B1220', 'fill-opacity': 0.55 };
const MAP_MASK = { 'fill-color': '#E8ECF1', 'fill-opacity': 0.72 };
const originals = new WeakMap();

function remember(map, layer, prop) {
  let store = originals.get(map);
  if (!store) originals.set(map, (store = {}));
  const key = `${layer}|${prop}`;
  if (!(key in store)) store[key] = map.getPaintProperty(layer, prop);
  return store[key];
}

/**
 * Switch the basemap. A raster basemap is shown as a hybrid: imagery under the vector roads,
 * boundaries and labels (labels turn white with a dark halo, roads fade, buildings hide).
 * The mask outside India darkens over imagery and lightens over the map.
 */
export function applyBasemap(map, basemaps, id) {
  const raster = basemaps.find((b) => b.id === id && b.tiles);
  basemaps
    .filter((b) => b.tiles)
    .forEach((b) => map.getLayer(`bm-${b.id}`) && map.setLayoutProperty(`bm-${b.id}`, 'visibility', b.id === id ? 'visible' : 'none'));
  const hybrid = Boolean(raster);
  map.getStyle().layers.forEach((l) => {
    const src = l['source-layer'];
    if (l.type === 'symbol' && src && l.layout?.['text-field'] !== undefined) {
      Object.entries(HYBRID_LABEL).forEach(([prop, value]) => {
        const orig = remember(map, l.id, prop);
        map.setPaintProperty(l.id, prop, hybrid ? value : orig);
      });
    } else if (l.type === 'line' && src === 'transportation') {
      const orig = remember(map, l.id, 'line-opacity');
      map.setPaintProperty(l.id, 'line-opacity', hybrid ? 0.45 : orig);
    } else if (src === 'building' && l.type === 'fill') {
      map.setLayoutProperty(l.id, 'visibility', hybrid ? 'none' : 'visible');
    }
  });
  if (map.getLayer('boundary-mask')) {
    const mask = hybrid ? HYBRID_MASK : MAP_MASK;
    Object.entries(mask).forEach(([prop, value]) => map.setPaintProperty('boundary-mask', prop, value));
  }
  if (map.getLayer('boundary-land')) map.setPaintProperty('boundary-land', 'line-color', hybrid ? '#FFFFFF' : '#1F2A3D');
  if (map.getLayer('boundary-eez')) map.setPaintProperty('boundary-eez', 'line-color', hybrid ? '#9CC3FF' : '#5B7FD6');
}

// Layer groups toggled together from the layer panel.
export const LAYER_GROUPS = {
  riskzones: ['riskzones-fill', 'riskzones-line'],
  footprints: ['footprints-fill', 'footprints-line'],
  landcover: ['landcover'],
  heat: ['hotspots-heat'],
  facilities: ['facilities-cluster', 'facilities-cluster-count', 'facilities'],
  clusters: ['clusters'],
  hotspots: ['hotspots'],
  incidents: ['incidents-halo', 'incidents'],
};

export const INTERACTIVE_LAYERS = ['incidents', 'clusters', 'riskzones-fill', 'facilities-cluster', 'facilities', 'footprints-fill', 'hotspots', 'landcover'];

export function dataLayers() {
  return [
    {
      id: 'riskzones-fill',
      type: 'fill',
      source: 'riskzones',
      paint: { 'fill-color': priorityColor, 'fill-opacity': 0.09 },
    },
    {
      id: 'riskzones-line',
      type: 'line',
      source: 'riskzones',
      paint: { 'line-color': priorityColor, 'line-width': 1.3, 'line-dasharray': [2, 1.5], 'line-opacity': 0.85 },
    },
    {
      id: 'footprints-fill',
      type: 'fill',
      source: 'footprints',
      minzoom: 8,
      paint: { 'fill-color': facilityColor, 'fill-opacity': 0.13 },
    },
    {
      id: 'footprints-line',
      type: 'line',
      source: 'footprints',
      minzoom: 8,
      paint: { 'line-color': facilityColor, 'line-width': 1.2, 'line-opacity': 0.8 },
    },
    {
      id: 'landcover',
      type: 'circle',
      source: 'landcover',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 3, 9, 6, 13, 12],
        'circle-color': ['coalesce', ['get', 'color'], '#999999'],
        'circle-opacity': 0.85,
        'circle-stroke-color': '#FFFFFF',
        'circle-stroke-width': 1,
      },
    },
    {
      id: 'hotspots-heat',
      type: 'heatmap',
      source: 'hotspots',
      maxzoom: 10,
      layout: { visibility: 'none' },
      paint: {
        'heatmap-weight': ['interpolate', ['linear'], ['coalesce', ['get', 'frp'], 0], 0, 0.15, 60, 1],
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 3, 0.6, 9, 1.6],
        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 3, 5, 9, 18],
        'heatmap-opacity': 0.75,
        'heatmap-color': [
          'interpolate',
          ['linear'],
          ['heatmap-density'],
          0,
          'rgba(252,211,77,0)',
          0.2,
          'rgba(252,211,77,0.55)',
          0.45,
          '#FB923C',
          0.7,
          '#EA580C',
          1,
          '#991B1B',
        ],
      },
    },
    {
      id: 'facilities-cluster',
      type: 'circle',
      source: 'facilities',
      filter: ['has', 'point_count'],
      paint: {
        'circle-color': '#FFFFFF',
        'circle-opacity': 0.92,
        'circle-stroke-color': '#4a3aa7',
        'circle-stroke-width': 1.5,
        'circle-radius': ['step', ['get', 'point_count'], 9, 20, 12, 100, 15, 500, 19],
      },
    },
    {
      id: 'facilities-cluster-count',
      type: 'symbol',
      source: 'facilities',
      filter: ['has', 'point_count'],
      layout: {
        'text-field': ['get', 'point_count_abbreviated'],
        'text-size': 10.5,
        'text-font': ['Noto Sans Bold'],
        'text-allow-overlap': true,
        // Never push basemap place names (cities, states) out of the way.
        'text-ignore-placement': true,
      },
      paint: { 'text-color': '#2E2470' },
    },
    {
      id: 'facilities',
      type: 'circle',
      source: 'facilities',
      filter: ['!', ['has', 'point_count']],
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 2.4, 8, 4, 12, 7],
        'circle-color': facilityColor,
        'circle-stroke-color': '#FFFFFF',
        'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 4, 0.6, 10, 1.5],
        'circle-opacity': 0.92,
      },
    },
    {
      id: 'clusters',
      type: 'circle',
      source: 'clusters',
      filter: ['any', ['>=', ['get', 'observation_count'], 2], ['==', ['get', 'industrial_association'], true]],
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, clusterRadius(0.55), 9, clusterRadius(1), 13, clusterRadius(1.5)],
        'circle-color': priorityColor,
        'circle-opacity': 0.12,
        'circle-stroke-color': priorityColor,
        'circle-stroke-width': 1.4,
        'circle-stroke-opacity': 0.9,
      },
    },
    {
      id: 'hotspots',
      type: 'circle',
      source: 'hotspots',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 1.7, 6, 2.6, 9, 4.5, 13, 8],
        'circle-color': frpColor,
        'circle-opacity': 0.92,
        'circle-stroke-color': ['interpolate', ['linear'], ['zoom'], 5, 'rgba(60,20,0,0.25)', 9, 'rgba(255,255,255,0.9)'],
        'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 5, 0.3, 9, 1],
      },
    },
    {
      id: 'incidents-halo',
      type: 'circle',
      source: 'incidents',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, ['*', 9, priorityScale], 10, ['*', 17, priorityScale]],
        'circle-color': priorityColor,
        'circle-opacity': 0.2,
      },
    },
    {
      id: 'incidents',
      type: 'circle',
      source: 'incidents',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, ['*', 4.5, priorityScale], 10, ['*', 7, priorityScale]],
        'circle-color': priorityColor,
        'circle-stroke-color': '#FFFFFF',
        'circle-stroke-width': 2,
      },
    },
    {
      id: 'selection',
      type: 'circle',
      source: 'selection',
      paint: {
        'circle-radius': 20,
        'circle-color': 'rgba(0,0,0,0)',
        'circle-stroke-color': '#1747B5',
        'circle-stroke-width': 2.5,
      },
    },
  ];
}

/**
 * Start the compact attribution collapsed (an "i" button) so it never spans the map. MapLibre
 * auto-expands it once sources register their attributions; collapse that first expansion
 * only, so the user can still open it. Returns a cleanup function.
 */
export function collapseAttribution(container) {
  const attrib = container.querySelector('.maplibregl-ctrl-attrib');
  if (!attrib) return () => {};
  let observer = null;
  const collapse = () => {
    if (attrib.classList.contains('maplibregl-compact-show')) {
      attrib.classList.remove('maplibregl-compact-show');
      observer?.disconnect();
    }
  };
  observer = new MutationObserver(collapse);
  observer.observe(attrib, { attributes: true, attributeFilter: ['class'] });
  collapse();
  return () => observer.disconnect();
}
