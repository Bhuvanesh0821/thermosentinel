import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AttributionControl,
  Map as MlMap,
  NavigationControl,
  Popup,
  ScaleControl,
  prewarm,
  setWorkerCount,
  setWorkerUrl,
} from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { api } from '../../api/client.js';
import { useApi } from '../../hooks/useApi.js';
import { filterParams, useApp } from '../../state/AppContext.jsx';
import { ErrorState, Spinner } from '../common/ui.jsx';
import {
  DATA_SOURCES,
  EMPTY_FC,
  SOURCE_OPTIONS,
  INTERACTIVE_LAYERS,
  LAYER_GROUPS,
  addRasterBasemaps,
  applyBasemap,
  boundaryLayers,
  dataLayers,
  firstSymbolLayer,
  hideBasemapBoundaries,
  loadBaseStyle,
  raisePlaceLabels,
} from './mapStyle.js';
import { clusterTooltip, facilityPopup, hotspotPopup, landcoverPopup } from './popups.js';
import LayerPanel from './LayerPanel.jsx';
import MapLegend from './MapLegend.jsx';
import MapFilters from './MapFilters.jsx';
import CoordinateReadout from './CoordinateReadout.jsx';
import s from './Map.module.css';

setWorkerUrl(workerUrl);
// Two workers are plenty for vector tiles at these zooms; start them now (in parallel with the
// API requests) instead of after the style arrives - this removes seconds from first paint.
setWorkerCount(2);
prewarm();

const DEFAULT_LAYERS = {
  hotspots: true,
  clusters: true,
  incidents: true,
  facilities: true,
  footprints: true,
  riskzones: true,
  landcover: false,
  heat: false,
};

const FOOTPRINT_MIN_ZOOM = 9;

export default function ThermalMap() {
  const { filters, selection, setSelection, mapFocus, setMapBounds, mapCommand, sendMapCommand } = useApp();
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const popupRef = useRef(null);
  const hoverPopupRef = useRef(null);
  const layersRef = useRef(DEFAULT_LAYERS);
  const [ready, setReady] = useState(false);
  const [layers, setLayers] = useState(DEFAULT_LAYERS);
  const [basemap, setBasemapState] = useState(() => {
    try {
      return window.localStorage.getItem('ts.basemap') || 'satellite';
    } catch {
      return 'satellite';
    }
  });
  const setBasemap = (id) => {
    setBasemapState(id);
    try {
      window.localStorage.setItem('ts.basemap', id);
    } catch {
      /* storage unavailable: choice lasts for this session only */
    }
  };
  const [footprintState, setFootprintState] = useState({ loading: false, error: null, count: 0, zoomOk: false });

  const config = useApi('/api/map/config', null, { live: false });
  // Shared filters drive every data layer (the map shows everything in view, so no bbox here).
  const shared = useMemo(() => filterParams({ ...filters, area: 'india' }, null), [filters]);
  const obsParams = useMemo(
    () => ({
      hours: filters.hours,
      ...filterParams({ ...filters, area: 'india' }, null, { detection: true }),
      limit: 20000,
    }),
    [filters],
  );
  const hotspots = useApi('/api/hotspots', obsParams, { enabled: layers.hotspots || layers.heat });
  const clusters = useApi(
    '/api/clusters',
    { format: 'geojson', hours: filters.hours, limit: 10000, ...shared },
    { enabled: layers.clusters },
  );
  const facilities = useApi(
    '/api/facilities',
    { format: 'geojson', limit: 20000, type: filters.facilityType.length ? filters.facilityType.join(',') : undefined },
    { enabled: layers.facilities },
  );
  const incidents = useApi(
    '/api/incidents',
    { format: 'geojson', status: 'active,monitoring', ...shared, confidence: undefined },
    { enabled: layers.incidents },
  );
  const riskzones = useApi('/api/risk-zones', null, { enabled: layers.riskzones });
  const landcover = useApi('/api/landcover', { limit: 20000 }, { enabled: layers.landcover });

  // ------------------------------------------------------------------ map init
  const [baseStyle, setBaseStyle] = useState(null);
  useEffect(() => {
    if (!config.data) return;
    let cancelled = false;
    loadBaseStyle(config.data.base_style_url).then((result) => !cancelled && setBaseStyle(result));
    return () => {
      cancelled = true;
    };
  }, [config.data]);

  useEffect(() => {
    if (!config.data || !baseStyle || mapRef.current || !containerRef.current) return undefined;
    const { region, basemaps } = config.data;
    const fit = region.land_bbox || region.bbox;
    const map = new MlMap({
      container: containerRef.current,
      style: structuredClone(baseStyle.style),
      bounds: [
        [fit[0], fit[1]],
        [fit[2], fit[3]],
      ],
      // Keep the view on India (with room for the EEZ and panels).
      maxBounds: [
        [region.bbox[0] - 12, region.bbox[1] - 8],
        [region.bbox[2] + 12, region.bbox[3] + 6],
      ],
      // Leave room for the floating Layers/Legend panels (left) and filter bar (top).
      // Clear the floating Layers panel only when the map is wide enough for it to matter.
      fitBoundsOptions: { padding: { top: 64, bottom: 24, left: containerRef.current.clientWidth >= 1000 ? 290 : 24, right: 24 } },
      attributionControl: false,
      maxZoom: 17,
      minZoom: 2,
      dragRotate: false,
      pitchWithRotate: false,
    });
    map.touchZoomRotate.disableRotation();
    if (import.meta.env.DEV) window.__thermoMap = map; // console debugging in development only
    map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right');
    map.addControl(new ScaleControl({ unit: 'metric', maxWidth: 110 }), 'bottom-right');
    map.addControl(
      new AttributionControl({
        compact: true,
        customAttribution:
          'NASA FIRMS · © OpenStreetMap contributors · ESA WorldCover · Natural Earth (India view) · Marine Regions EEZ (CC BY)',
      }),
      'bottom-right',
    );
    // Start the compact attribution collapsed (an "i" button) so it never spans the map.
    // MapLibre auto-expands it (class `maplibregl-compact-show`) once sources register their
    // attributions; collapse that first auto-expansion only, so the user can still toggle it.
    const attrib = containerRef.current.querySelector('.maplibregl-ctrl-attrib');
    let attribObserver = null;
    if (attrib) {
      const collapse = () => {
        if (attrib.classList.contains('maplibregl-compact-show')) {
          attrib.classList.remove('maplibregl-compact-show');
          attribObserver?.disconnect();
        }
      };
      attribObserver = new MutationObserver(collapse);
      attribObserver.observe(attrib, { attributes: true, attributeFilter: ['class'] });
      collapse(); // custom attribution makes MapLibre expand it synchronously in addControl
    }
    mapRef.current = map;

    // Set up as soon as the style is parsed; `load` would also wait for every basemap tile.
    // The last `styledata` event can fire just before isStyleLoaded() flips to true, so also try
    // on `load` and `idle`; whichever first sees a ready style runs the setup (exactly once).
    let initialised = false;
    const trySetup = () => {
      if (initialised || !map.isStyleLoaded()) return;
      initialised = true;
      map.off('style.load', trySetup);
      map.off('styledata', trySetup);
      map.off('load', trySetup);
      map.off('idle', trySetup);
      setup();
    };
    map.on('style.load', trySetup);
    map.on('styledata', trySetup);
    map.on('load', trySetup);
    map.on('idle', trySetup);
    // MapLibre can finish loading the sprite after its last style event; poll as a fallback.
    const setupPoll = window.setInterval(() => {
      trySetup();
      if (initialised) window.clearInterval(setupPoll);
    }, 250);

    function setup() {
      hideBasemapBoundaries(map);
      const labels = firstSymbolLayer(map);
      addRasterBasemaps(map, basemaps, labels);
      DATA_SOURCES.forEach((id) => map.addSource(id, { type: 'geojson', data: EMPTY_FC, ...(SOURCE_OPTIONS[id] || {}) }));
      // Mask + official boundary under the basemap labels; data layers on top of everything.
      boundaryLayers().forEach((layer) => map.addLayer(layer, labels));
      // Count labels need the basemap's glyphs; the plain fallback style has none.
      const hasGlyphs = Boolean(map.getStyle().glyphs);
      dataLayers()
        .filter((layer) => hasGlyphs || layer.type !== 'symbol')
        .forEach((layer) => map.addLayer(layer));
      raisePlaceLabels(map);
      api
        .get('/api/map/boundary')
        .then(({ data }) => map.getSource('boundary')?.setData(data))
        .catch(() => {});
      Object.entries(LAYER_GROUPS).forEach(([group, ids]) =>
        ids.forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', layersRef.current[group] ? 'visible' : 'none')),
      );
      setReady(true);
    }

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(containerRef.current);
    return () => {
      window.clearInterval(setupPoll);
      ro.disconnect();
      attribObserver?.disconnect();
      popupRef.current?.remove();
      hoverPopupRef.current?.remove();
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, [config.data, baseStyle]);

  // ------------------------------------------------------------ interactions
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return undefined;

    const openPopup = (lngLat, html) => {
      popupRef.current?.remove();
      const popup = new Popup({ maxWidth: '320px', closeButton: true, offset: 10 }).setLngLat(lngLat).setHTML(html).addTo(map);
      popup.getElement().addEventListener('click', (ev) => {
        const target = ev.target.closest('[data-cluster]');
        if (target) {
          setSelection({ type: 'cluster', id: Number(target.dataset.cluster) });
          popup.remove();
        }
      });
      popupRef.current = popup;
    };

    const onClick = (ev) => {
      const active = INTERACTIVE_LAYERS.filter((id) => map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== 'none');
      const features = map.queryRenderedFeatures(ev.point, { layers: active });
      if (!features.length) return;
      const byLayer = (id) => features.find((f) => f.layer.id === id);
      const incident = byLayer('incidents');
      const cluster = byLayer('clusters');
      const zone = byLayer('riskzones-fill');
      const facility = byLayer('facilities');
      const facilityGroup = byLayer('facilities-cluster');
      const footprint = byLayer('footprints-fill');
      const hotspot = byLayer('hotspots');
      const lc = byLayer('landcover');
      if (incident) {
        setSelection({ type: 'cluster', id: incident.properties.cluster_id, incidentId: incident.properties.id });
      } else if (hotspot) {
        openPopup(
          ev.lngLat,
          hotspotPopup(
            hotspot.properties,
            hotspot.geometry.coordinates ? { lng: hotspot.geometry.coordinates[0], lat: hotspot.geometry.coordinates[1] } : ev.lngLat,
          ),
        );
      } else if (cluster) {
        setSelection({ type: 'cluster', id: cluster.properties.id });
      } else if (facilityGroup) {
        // Expand a facility cluster: zoom to where it splits.
        map
          .getSource('facilities')
          .getClusterExpansionZoom(facilityGroup.properties.cluster_id)
          .then((zoom) => map.easeTo({ center: facilityGroup.geometry.coordinates, zoom: zoom + 0.2 }))
          .catch(() => {});
      } else if (facility) {
        const [lng, lat] = facility.geometry.coordinates;
        openPopup({ lng, lat }, facilityPopup(facility.properties, { lng, lat }));
      } else if (lc) {
        openPopup(ev.lngLat, landcoverPopup(lc.properties));
      } else if (zone) {
        setSelection({ type: 'cluster', id: zone.properties.cluster_id, incidentId: zone.properties.incident_id });
      } else if (footprint) {
        api
          .get(`/api/facilities/${footprint.properties.id}`)
          .then(({ data }) =>
            openPopup(
              ev.lngLat,
              facilityPopup(
                {
                  ...data,
                  type: data.facility_type,
                  type_label: data.facility_type_label,
                  subtype: data.facility_subtype,
                  has_footprint: true,
                },
                { lng: data.longitude, lat: data.latitude },
              ),
            ),
          )
          .catch(() => {});
      }
    };

    const onMove = (ev) => {
      const active = INTERACTIVE_LAYERS.filter((id) => map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== 'none');
      const features = map.queryRenderedFeatures(ev.point, { layers: active });
      map.getCanvas().style.cursor = features.length ? 'pointer' : '';
      const cluster = features.find((f) => f.layer.id === 'clusters');
      if (cluster && !features.find((f) => f.layer.id === 'hotspots')) {
        if (!hoverPopupRef.current) {
          hoverPopupRef.current = new Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'ts-hover' });
        }
        hoverPopupRef.current.setLngLat(cluster.geometry.coordinates).setHTML(clusterTooltip(cluster.properties)).addTo(map);
      } else {
        hoverPopupRef.current?.remove();
      }
    };

    map.on('click', onClick);
    map.on('mousemove', onMove);
    map.on('mouseout', () => hoverPopupRef.current?.remove());
    return () => {
      map.off('click', onClick);
      map.off('mousemove', onMove);
    };
  }, [ready, setSelection]);

  // ------------------------------------------------------------- data binding
  const bind = (source, fc) => {
    const map = mapRef.current;
    if (!ready || !map?.getSource(source)) return;
    map.getSource(source).setData(fc || EMPTY_FC);
  };
  useEffect(() => bind('hotspots', hotspots.data), [ready, hotspots.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => bind('clusters', clusters.data), [ready, clusters.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => bind('facilities', facilities.data), [ready, facilities.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => bind('incidents', incidents.data), [ready, incidents.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => bind('riskzones', riskzones.data), [ready, riskzones.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => bind('landcover', landcover.data), [ready, landcover.data]); // eslint-disable-line react-hooks/exhaustive-deps

  // Footprints are fetched for the visible extent only (they are large polygons).
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return undefined;
    let controller = null;
    let timer = null;
    const load = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const zoomOk = map.getZoom() >= FOOTPRINT_MIN_ZOOM;
        if (!layersRef.current.footprints || !zoomOk) {
          map.getSource('footprints')?.setData(EMPTY_FC);
          setFootprintState({ loading: false, error: null, count: 0, zoomOk });
          return;
        }
        controller?.abort();
        controller = new AbortController();
        const b = map.getBounds();
        const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(5)).join(',');
        setFootprintState((st) => ({ ...st, loading: true, zoomOk }));
        api
          .get('/api/facilities/footprints', { bbox }, controller.signal)
          .then(({ data }) => {
            map.getSource('footprints')?.setData(data);
            setFootprintState({ loading: false, error: null, count: data.features.length, zoomOk });
          })
          .catch((error) => {
            if (error.name !== 'AbortError') setFootprintState({ loading: false, error, count: 0, zoomOk });
          });
      }, 350);
    };
    map.on('moveend', load);
    load();
    return () => {
      map.off('moveend', load);
      window.clearTimeout(timer);
      controller?.abort();
    };
  }, [ready, layers.footprints]);

  // Visible extent -> shared state (drives the "Map view" area filter of the panels).
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return undefined;
    let timer = null;
    const report = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const b = map.getBounds();
        setMapBounds([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(3)).join(','));
      }, 400);
    };
    map.on('moveend', report);
    report();
    return () => {
      map.off('moveend', report);
      window.clearTimeout(timer);
    };
  }, [ready, setMapBounds]);

  // --------------------------------------------------------- layer visibility
  useEffect(() => {
    layersRef.current = layers;
    const map = mapRef.current;
    if (!ready || !map) return;
    Object.entries(LAYER_GROUPS).forEach(([group, ids]) =>
      ids.forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', layers[group] ? 'visible' : 'none')),
    );
  }, [layers, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !config.data) return;
    const known = config.data.basemaps.some((b) => b.id === basemap);
    applyBasemap(map, config.data.basemaps, known ? basemap : 'satellite');
  }, [basemap, ready, config.data]);

  // ------------------------------------------------------ focus + selection
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !mapFocus) return;
    if (mapFocus.bbox) {
      // A named area (state, city): show all of it, zooming out if needed.
      const [w, s, e, n] = mapFocus.bbox;
      map.fitBounds(
        [
          [w, s],
          [e, n],
        ],
        { padding: 40, maxZoom: 12, duration: 1400, essential: true },
      );
    } else {
      map.flyTo({ center: [mapFocus.lon, mapFocus.lat], zoom: Math.max(map.getZoom(), mapFocus.zoom), speed: 1.5, essential: true });
    }
  }, [mapFocus, ready]);

  // Commands from elsewhere in the app (voice): switch basemap, turn layers on. Applied once.
  useEffect(() => {
    if (!mapCommand) return;
    if (mapCommand.basemap) setBasemap(mapCommand.basemap);
    if (mapCommand.layers) setLayers((l) => ({ ...l, ...mapCommand.layers }));
    sendMapCommand(null);
  }, [mapCommand]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    let point = null;
    if (selection?.type === 'cluster') {
      const f = clusters.data?.features.find((x) => x.properties.id === selection.id);
      if (f) point = f.geometry.coordinates;
    }
    if (!point && selection?.lon != null) point = [selection.lon, selection.lat];
    map
      .getSource('selection')
      ?.setData(
        point
          ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: point }, properties: {} }] }
          : EMPTY_FC,
      );
  }, [selection, clusters.data, ready]);

  // ----------------------------------------------------------------- render
  const layerStates = {
    hotspots: hotspots,
    heat: hotspots,
    clusters: clusters,
    incidents: incidents,
    facilities: facilities,
    riskzones: riskzones,
    landcover: landcover,
    footprints: {
      loading: footprintState.loading,
      error: footprintState.error,
      data: null,
      meta: { count: footprintState.count },
      note: footprintState.zoomOk ? null : `Zoom ≥ ${FOOTPRINT_MIN_ZOOM}`,
    },
  };

  const blockingError = hotspots.error || clusters.error;
  const noDetections = hotspots.data && hotspots.data.features.length === 0 && !hotspots.loading;

  return (
    <div className={s.wrap}>
      <div ref={containerRef} className={s.map} aria-label="Thermal intelligence map" role="region" />
      {config.error && (
        <div className={s.overlayCenter}>
          <div className={s.overlayCard}>
            <ErrorState error={config.error} onRetry={config.reload} center />
          </div>
        </div>
      )}
      {!config.error && !ready && (
        <div className={s.overlayCenter}>
          <div className={s.loadingChip}>
            <Spinner /> Initialising map
          </div>
        </div>
      )}
      {ready && blockingError && (
        <div className={s.overlayCenter}>
          <div className={s.overlayCard}>
            <ErrorState
              error={blockingError}
              onRetry={() => {
                hotspots.reload();
                clusters.reload();
              }}
              center
            />
          </div>
        </div>
      )}
      {ready && (
        <div className={s.banners}>
          {baseStyle && !baseStyle.ok && (
            <div className={s.banner} role="status">
              Vector basemap unavailable — showing data on a plain background. Other basemaps remain selectable.
            </div>
          )}
          {!blockingError && noDetections && (
            <div className={s.banner} role="status">
              No FIRMS detections stored for the selected window and filters.
              {hotspots.meta?.total === 0 && filters.hours < 168 ? ' Try a longer window.' : ''}
            </div>
          )}
          {hotspots.meta?.truncated && (
            <div className={s.banner} role="status">
              Showing the {hotspots.data.features.length.toLocaleString()} most intense of {hotspots.meta.total.toLocaleString()}{' '}
              detections. Raise the minimum FRP or shorten the window to see all.
            </div>
          )}
        </div>
      )}
      <LayerPanel
        layers={layers}
        setLayers={setLayers}
        basemap={basemap}
        setBasemap={setBasemap}
        basemaps={config.data?.basemaps || []}
        states={layerStates}
      />
      <MapFilters />
      <MapLegend layers={layers} landCoverClasses={config.data?.land_cover_classes || []} />
      {ready && <CoordinateReadout map={mapRef.current} />}
    </div>
  );
}
