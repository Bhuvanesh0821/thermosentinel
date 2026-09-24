import { useEffect, useMemo, useRef, useState } from 'react';
import { AttributionControl, Map as MlMap, NavigationControl, Popup, setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { api } from '../../api/client.js';
import { useApi } from '../../hooks/useApi.js';
import { fmtInt, fmtNum } from '../../utils/format.js';
import { ErrorState, Spinner } from '../common/ui.jsx';
import { EMPTY_FC, boundaryLayers, firstSymbolLayer, collapseAttribution, hideBasemapBoundaries, loadBaseStyle } from './mapStyle.js';
import s from './GridMap.module.css';

setWorkerUrl(workerUrl);

// Sequential single-hue ramp (light -> dark), validated with the dataviz ordinal checks.
export const GRID_RAMP = ['#86b6ef', '#3987e5', '#1c5cab', '#0d366b'];

/** Class breaks at the 50th/80th/95th percentile of cell counts (at least 1 apart). */
export function gridBreaks(features) {
  const vals = features.map((f) => f.properties.detections).sort((a, b) => a - b);
  if (!vals.length) return [];
  const q = (p) => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))];
  const out = [];
  [q(0.5), q(0.8), q(0.95)].forEach((v) => {
    const b = Math.max(v + 1, (out.at(-1) ?? 1) + 1);
    if (b <= vals.at(-1)) out.push(b);
  });
  return out;
}

/** Detections binned into degree cells across India (from /api/analytics/grid). */
export default function GridMap({ grid }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [baseStyle, setBaseStyle] = useState(null);
  const config = useApi('/api/map/config', null, { live: false });
  const breaks = useMemo(() => gridBreaks(grid?.features || []), [grid]);

  useEffect(() => {
    if (!config.data) return undefined;
    let cancelled = false;
    loadBaseStyle(config.data.base_style_url).then((r) => !cancelled && setBaseStyle(r));
    return () => {
      cancelled = true;
    };
  }, [config.data]);

  useEffect(() => {
    if (!config.data || !baseStyle || mapRef.current || !containerRef.current) return undefined;
    const { region } = config.data;
    const fit = region.land_bbox || region.bbox;
    const map = new MlMap({
      container: containerRef.current,
      style: structuredClone(baseStyle.style),
      bounds: [
        [fit[0], fit[1]],
        [fit[2], fit[3]],
      ],
      fitBoundsOptions: { padding: 16 },
      attributionControl: false,
      maxZoom: 9,
      minZoom: 2,
      dragRotate: false,
      pitchWithRotate: false,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right');
    map.addControl(
      new AttributionControl({
        compact: true,
        customAttribution: 'NASA FIRMS · © OpenStreetMap contributors · Natural Earth (India view)',
      }),
      'bottom-right',
    );
    const uncollapse = collapseAttribution(containerRef.current);
    mapRef.current = map;
    let done = false;
    const setup = () => {
      if (done || !map.isStyleLoaded()) return;
      done = true;
      hideBasemapBoundaries(map);
      // The card can still be laying out when the map is created: refit to India once ready.
      map.resize();
      map.fitBounds(
        [
          [fit[0], fit[1]],
          [fit[2], fit[3]],
        ],
        { padding: 16, duration: 0 },
      );
      const labels = firstSymbolLayer(map);
      map.addSource('boundary', { type: 'geojson', data: EMPTY_FC });
      map.addSource('grid', { type: 'geojson', data: EMPTY_FC });
      map.addLayer({ id: 'grid-fill', type: 'fill', source: 'grid', paint: { 'fill-color': GRID_RAMP[0], 'fill-opacity': 0.82 } }, labels);
      map.addLayer({ id: 'grid-line', type: 'line', source: 'grid', paint: { 'line-color': '#ffffff', 'line-width': 0.6 } }, labels);
      boundaryLayers().forEach((layer) => map.addLayer(layer, labels));
      api
        .get('/api/map/boundary')
        .then(({ data }) => map.getSource('boundary')?.setData(data))
        .catch(() => {});
      const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 6 });
      map.on('mousemove', 'grid-fill', (e) => {
        map.getCanvas().style.cursor = 'default';
        const p = e.features[0].properties;
        const south = Number(p.south);
        const west = Number(p.west);
        const c = Number(p.cell_deg);
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<div class="ts-pop ts-pop-compact"><div class="ts-pop-title">${fmtInt(Number(p.detections))} detections</div>` +
              `<div class="ts-pop-muted">${fmtInt(Number(p.clusters))} cluster(s) · max FRP ${fmtNum(Number(p.max_frp))} MW</div>` +
              `<div class="ts-pop-muted">${south.toFixed(1)}–${(south + c).toFixed(1)}°N, ${west.toFixed(1)}–${(west + c).toFixed(1)}°E</div></div>`,
          )
          .addTo(map);
      });
      map.on('mouseleave', 'grid-fill', () => popup.remove());
      setReady(true);
    };
    ['style.load', 'styledata', 'load', 'idle'].forEach((ev) => map.on(ev, setup));
    const poll = window.setInterval(() => {
      setup();
      if (done) window.clearInterval(poll);
    }, 250);
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(containerRef.current);
    return () => {
      window.clearInterval(poll);
      ro.disconnect();
      uncollapse();
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, [config.data, baseStyle]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.getSource('grid')?.setData(grid || EMPTY_FC);
    const color = ['step', ['get', 'detections'], GRID_RAMP[0]];
    breaks.forEach((b, i) => color.push(b, GRID_RAMP[i + 1]));
    map.setPaintProperty('grid-fill', 'fill-color', breaks.length ? color : GRID_RAMP[0]);
  }, [ready, grid, breaks]);

  const maxVal = Math.max(0, ...(grid?.features || []).map((f) => f.properties.detections));
  const classes = [1, ...breaks].map((lo, i, arr) => ({ color: GRID_RAMP[i], lo, hi: i < arr.length - 1 ? arr[i + 1] - 1 : maxVal }));

  return (
    <div className={s.wrap}>
      <div ref={containerRef} className={s.map} role="region" aria-label="Geographic distribution of detections" />
      {!ready && !config.error && (
        <div className={s.overlay}>
          <Spinner label="Loading map" />
        </div>
      )}
      {config.error && (
        <div className={s.overlay}>
          <ErrorState error={config.error} onRetry={config.reload} compact />
        </div>
      )}
      {grid?.features?.length > 0 && (
        <div className={s.legend}>
          <div className={s.legendTitle}>Detections per cell</div>
          {classes.map((c) => (
            <div key={c.color} className={s.legendRow}>
              <span className={s.sw} style={{ background: c.color }} />
              <span className="mono">{c.lo === c.hi ? fmtInt(c.lo) : `${fmtInt(c.lo)}–${fmtInt(c.hi)}`}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
