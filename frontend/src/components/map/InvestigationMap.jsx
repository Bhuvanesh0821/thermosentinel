import { useEffect, useMemo, useRef, useState } from 'react';
import { AttributionControl, Map as MlMap, NavigationControl, Popup, ScaleControl, setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { api } from '../../api/client.js';
import { useApi } from '../../hooks/useApi.js';
import { FRP_STOPS } from '../../utils/constants.js';
import { escapeHtml, fmtNum, fmtUtc } from '../../utils/format.js';
import { ErrorState, Segmented, Spinner } from '../common/ui.jsx';
import { EMPTY_FC, addRasterBasemaps, applyBasemap, boundaryLayers, firstSymbolLayer, collapseAttribution, hideBasemapBoundaries, loadBaseStyle } from './mapStyle.js';
import s from './InvestigationMap.module.css';

setWorkerUrl(workerUrl);

const frpColor = ['interpolate', ['linear'], ['coalesce', ['get', 'frp'], 0], ...FRP_STOPS.flat()];

function toCollections({ observations, cluster, facility }) {
  const detections = {
    type: 'FeatureCollection',
    features: (observations || []).map((o) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [o.longitude, o.latitude] },
      properties: { frp: o.frp, at: o.acquired_at, sat: o.satellite_name, dn: o.daynight, conf: o.confidence_level },
    })),
  };
  const hull = cluster?.hull
    ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: cluster.hull, properties: {} }] }
    : EMPTY_FC;
  const fac = facility
    ? {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [facility.longitude, facility.latitude] },
            properties: { role: 'point' },
          },
          ...(facility.footprint ? [{ type: 'Feature', geometry: facility.footprint, properties: { role: 'footprint' } }] : []),
        ],
      }
    : EMPTY_FC;
  return { detections, hull, fac };
}

function extent(observations, cluster, facility) {
  const pts = (observations || []).map((o) => [o.longitude, o.latitude]);
  if (facility) pts.push([facility.longitude, facility.latitude]);
  if (!pts.length && cluster) pts.push([cluster.center_longitude, cluster.center_latitude]);
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const pad = 0.01;
  return [
    [Math.min(...xs) - pad, Math.min(...ys) - pad],
    [Math.max(...xs) + pad, Math.max(...ys) + pad],
  ];
}

/** Focused map of one incident: member detections (FRP colour), cluster outline and the facility. */
export default function InvestigationMap({ observations, cluster, facility }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [base, setBase] = useState('satellite');
  const [baseStyle, setBaseStyle] = useState(null);
  const config = useApi('/api/map/config', null, { live: false });
  const data = useMemo(() => toCollections({ observations, cluster, facility }), [observations, cluster, facility]);

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
    const map = new MlMap({
      container: containerRef.current,
      style: structuredClone(baseStyle.style),
      bounds: extent(observations, cluster, facility),
      fitBoundsOptions: { padding: 48, maxZoom: 14 },
      attributionControl: false,
      maxZoom: 17,
      dragRotate: false,
      pitchWithRotate: false,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right');
    map.addControl(new ScaleControl({ unit: 'metric', maxWidth: 100 }), 'bottom-left');
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
      const labels = firstSymbolLayer(map);
      addRasterBasemaps(map, config.data.basemaps, labels);
      map.addSource('boundary', { type: 'geojson', data: EMPTY_FC });
      boundaryLayers().forEach((layer) => map.addLayer(layer, labels));
      map.addSource('hull', { type: 'geojson', data: EMPTY_FC });
      map.addSource('facility', { type: 'geojson', data: EMPTY_FC });
      map.addSource('detections', { type: 'geojson', data: EMPTY_FC });
      map.addLayer({
        id: 'fac-fill',
        type: 'fill',
        source: 'facility',
        filter: ['==', ['get', 'role'], 'footprint'],
        paint: { 'fill-color': '#4a3aa7', 'fill-opacity': 0.14 },
      });
      map.addLayer({
        id: 'fac-line',
        type: 'line',
        source: 'facility',
        filter: ['==', ['get', 'role'], 'footprint'],
        paint: { 'line-color': '#4a3aa7', 'line-width': 2 },
      });
      map.addLayer({ id: 'hull-fill', type: 'fill', source: 'hull', paint: { 'fill-color': '#ad3a16', 'fill-opacity': 0.08 } });
      map.addLayer({
        id: 'hull-line',
        type: 'line',
        source: 'hull',
        paint: { 'line-color': '#ad3a16', 'line-width': 1.5, 'line-dasharray': [3, 2] },
      });
      map.addLayer({
        id: 'fac-point',
        type: 'circle',
        source: 'facility',
        filter: ['==', ['get', 'role'], 'point'],
        paint: { 'circle-radius': 6, 'circle-color': '#4a3aa7', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 },
      });
      map.addLayer({
        id: 'detections',
        type: 'circle',
        source: 'detections',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 4, 14, 8],
          'circle-color': frpColor,
          'circle-stroke-color': ['match', ['get', 'dn'], 'N', '#1F2A3D', '#ffffff'],
          'circle-stroke-width': 1.5,
          'circle-opacity': 0.92,
        },
      });
      api
        .get('/api/map/boundary')
        .then(({ data: b }) => map.getSource('boundary')?.setData(b))
        .catch(() => {});
      const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 8 });
      map.on('mousemove', 'detections', (e) => {
        map.getCanvas().style.cursor = 'pointer';
        const p = e.features[0].properties;
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<div class="ts-pop"><b>${escapeHtml(p.sat)}</b> · ${p.dn === 'N' ? 'night' : 'day'}<br/>${fmtUtc(p.at)}<br/>FRP <b>${fmtNum(Number(p.frp))} MW</b> · ${escapeHtml(p.conf || '')} confidence</div>`,
          )
          .addTo(map);
      });
      map.on('mouseleave', 'detections', () => {
        map.getCanvas().style.cursor = '';
        popup.remove();
      });
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
  }, [config.data, baseStyle]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.getSource('detections')?.setData(data.detections);
    map.getSource('hull')?.setData(data.hull);
    map.getSource('facility')?.setData(data.fac);
  }, [ready, data]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !config.data) return;
    applyBasemap(map, config.data.basemaps, base);
  }, [ready, base, config.data]);

  const hasSatellite = (config.data?.basemaps || []).some((b) => b.id === 'satellite' && b.tiles);

  return (
    <div className={s.wrap}>
      <div ref={containerRef} className={s.map} aria-label="Incident map" role="region" />
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
      {hasSatellite && (
        <div className={s.baseSwitch}>
          <Segmented
            label="Basemap"
            value={base}
            onChange={setBase}
            options={[
              { value: 'map', label: 'Map' },
              { value: 'satellite', label: 'Satellite' },
            ]}
          />
        </div>
      )}
      <div className={s.legend}>
        <span>
          <i className={s.swDet} /> Detection (colour = FRP, dark ring = night)
        </span>
        <span>
          <i className={s.swHull} /> Cluster extent
        </span>
        {facility && (
          <span>
            <i className={s.swFac} /> Facility{facility.footprint ? ' & footprint' : ''}
          </span>
        )}
      </div>
    </div>
  );
}
