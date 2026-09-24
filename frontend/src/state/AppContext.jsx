import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { streamUrl, wsUrl } from '../api/client.js';

const AppContext = createContext(null);

// Events after which data shown on screen may have changed.
const DATA_EVENTS = new Set([
  'pipeline.completed',
  'analysis.completed',
  'ingestion.firms.completed',
  'ingestion.facilities.completed',
  'ingestion.facilities.progress',
  'alert.created',
  'alert.escalated',
  'alert.acknowledged',
  'alert.resolved',
  'maintenance.retention',
  'region.updated',
]);

export const DEFAULT_FILTERS = {
  hours: 48,
  minFrp: null,
  confidence: null,
  instrument: null,
  daynight: null,
  minPriority: null,
  classification: [],
  facilityType: [],
  persistence: [],
  area: 'india', // 'india' | 'view' | 'place'
  placeBbox: null, // [west, south, east, north] when area === 'place' (e.g. a state named by voice)
  placeName: null,
};

/** Map shared filters onto API query parameters (only the ones each endpoint understands). */
export function filterParams(filters, mapBounds, { detection = false } = {}) {
  const p = {
    min_priority: filters.minPriority || undefined,
    classification: filters.classification.length ? filters.classification.join(',') : undefined,
    facility_type: filters.facilityType.length ? filters.facilityType.join(',') : undefined,
    persistence: filters.persistence.length ? filters.persistence.join(',') : undefined,
    confidence: filters.confidence || undefined,
    bbox:
      filters.area === 'view' && mapBounds
        ? mapBounds
        : filters.area === 'place' && filters.placeBbox
          ? filters.placeBbox.map((v) => Number(v).toFixed(4)).join(',')
          : undefined,
  };
  if (detection) {
    Object.assign(p, {
      min_frp: filters.minFrp || undefined,
      instrument: filters.instrument || undefined,
      daynight: filters.daynight || undefined,
    });
  }
  return p;
}

function readPref(key, fallback) {
  try {
    const v = window.localStorage.getItem(key);
    return v === null ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}
function writePref(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable (private mode): preference simply isn't persisted */
  }
}

export function AppProvider({ children }) {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [mapBounds, setMapBounds] = useState(null);
  const [selection, setSelection] = useState(null); // { type: 'cluster' | 'facility', id, incidentId?, lon?, lat? }
  const [mapFocus, setMapFocus] = useState(null);
  const [mapCommand, setMapCommand] = useState(null); // { basemap?, layers?, key } - e.g. from a voice command
  const [refreshKey, setRefreshKey] = useState(0);
  const [stream, setStream] = useState({ status: 'connecting', transport: null, lastEvent: null, lastEventAt: null });
  const [pipeline, setPipeline] = useState({ running: false, job: null, progress: null });
  const [toasts, setToasts] = useState([]);
  const [browserNotify, setBrowserNotifyState] = useState(() => readPref('ts.browserNotifications', false));
  const refreshTimer = useRef(null);
  const notifyRef = useRef(browserNotify);
  const navigateRef = useRef(null); // set by <NavigationBridge/> inside the router

  const refresh = useCallback(() => {
    window.clearTimeout(refreshTimer.current);
    refreshTimer.current = window.setTimeout(() => setRefreshKey((k) => k + 1), 600);
  }, []);

  const pushToast = useCallback((toast) => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((list) => [...list.slice(-3), { id, ...toast }]);
    window.setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), toast.timeout || 7000);
  }, []);
  const dismissToast = useCallback((id) => setToasts((list) => list.filter((t) => t.id !== id)), []);

  const focusMap = useCallback((lon, lat, zoom = 11, bbox = null) => setMapFocus({ lon, lat, zoom, bbox, key: Date.now() }), []);
  const sendMapCommand = useCallback((cmd) => setMapCommand(cmd ? { ...cmd, key: Date.now() } : null), []);

  const setBrowserNotify = useCallback((on) => {
    notifyRef.current = on;
    setBrowserNotifyState(on);
    writePref('ts.browserNotifications', on);
  }, []);

  const handleMessage = useCallback(
    (message) => {
      const type = message.type;
      if (!type || type === 'heartbeat') return;
      const payload = message.payload || {};
      setStream((s) => ({ ...s, status: 'live', lastEvent: type, lastEventAt: new Date().toISOString() }));
      if (type === 'pipeline.started') setPipeline({ running: true, job: 'pipeline', progress: null });
      if (type === 'pipeline.completed') setPipeline({ running: false, job: null, progress: null });
      if (type === 'ingestion.facilities.progress') {
        setPipeline((p) => ({ ...p, running: true, job: 'facilities_ingest', progress: `${payload.tile}/${payload.of} tiles` }));
      }
      if (DATA_EVENTS.has(type)) refresh();
      if (type === 'alert.created' || type === 'alert.escalated') {
        const title = type === 'alert.created' ? 'New alert' : 'Alert escalated';
        pushToast({
          tone: payload.severity || 'medium',
          title,
          body: payload.title,
          link: payload.incident_id ? `/investigation/${payload.incident_id}` : '/alerts',
        });
        if (notifyRef.current && 'Notification' in window && Notification.permission === 'granted') {
          try {
            const n = new Notification(`ThermoSentinel · ${title} (${payload.severity})`, {
              body: payload.title,
              tag: `ts-alert-${payload.alert_id}-${type}`,
            });
            n.onclick = () => {
              window.focus();
              if (payload.incident_id) navigateRef.current?.(`/investigation/${payload.incident_id}`);
            };
          } catch {
            /* notifications blocked by the browser */
          }
        }
      }
      if (type === 'analysis.completed' || type === 'ingestion.firms.completed' || type.endsWith('.failed')) {
        pushToast({ tone: type.endsWith('failed') ? 'error' : 'info', title: 'Pipeline update', body: payload.message, timeout: 5000 });
      }
    },
    [refresh, pushToast],
  );

  // Live updates: WebSocket first, Server-Sent Events as automatic fallback.
  useEffect(() => {
    let ws = null;
    let es = null;
    let closed = false;
    let failures = 0;
    let retryTimer = null;

    let everConnected = false;
    // After any reconnect, refetch: events published while disconnected (e.g. during an API
    // redeploy or a platform restart) were missed.
    const connected = (transport) => {
      if (everConnected) refresh();
      everConnected = true;
      setStream((s) => ({ ...s, status: 'live', transport }));
    };

    const startSse = () => {
      es = new EventSource(streamUrl());
      es.onopen = () => connected('sse');
      es.onerror = () => setStream((s) => ({ ...s, status: es.readyState === 2 ? 'offline' : 'reconnecting' }));
      const names = [
        'hello',
        'pipeline.started',
        'pipeline.completed',
        'analysis.completed',
        'analysis.failed',
        'ingestion.firms.completed',
        'ingestion.firms.failed',
        'ingestion.facilities.completed',
        'ingestion.facilities.progress',
        'ingestion.facilities.failed',
        'alert.created',
        'alert.escalated',
        'alert.acknowledged',
        'alert.resolved',
        'maintenance.retention',
        'region.updated',
      ];
      names.forEach((n) =>
        es.addEventListener(n, (e) => {
          try {
            handleMessage(JSON.parse(e.data));
          } catch {
            /* ignore malformed event */
          }
        }),
      );
    };

    const startWs = () => {
      try {
        ws = new WebSocket(wsUrl('/ws/stream'));
      } catch {
        startSse();
        return;
      }
      ws.onopen = () => {
        failures = 0;
        if (es) {
          es.close(); // WebSocket is back: retire the SSE fallback
          es = null;
        }
        connected('websocket');
      };
      ws.onmessage = (e) => {
        try {
          handleMessage(JSON.parse(e.data));
        } catch {
          /* ignore malformed message */
        }
      };
      ws.onclose = () => {
        if (closed) return;
        failures += 1;
        if (failures === 3 && !es) {
          // Proxies that block WebSockets: fall back to SSE, and keep probing for WebSocket slowly.
          setStream((s) => ({ ...s, status: 'reconnecting', transport: 'sse' }));
          startSse();
        } else if (!es) {
          setStream((s) => ({ ...s, status: 'reconnecting' }));
        }
        retryTimer = window.setTimeout(startWs, Math.min(1500 * 2 ** Math.min(failures - 1, 5), 60000));
      };
    };

    startWs();
    return () => {
      closed = true;
      window.clearTimeout(retryTimer);
      ws?.close();
      es?.close();
    };
  }, [handleMessage, refresh]);

  const value = useMemo(
    () => ({
      filters,
      setFilters,
      mapBounds,
      setMapBounds,
      selection,
      setSelection,
      mapFocus,
      focusMap,
      mapCommand,
      sendMapCommand,
      refreshKey,
      refresh,
      stream,
      pipeline,
      setPipeline,
      toasts,
      pushToast,
      dismissToast,
      browserNotify,
      setBrowserNotify,
      navigateRef,
    }),
    [
      filters,
      mapBounds,
      selection,
      mapFocus,
      focusMap,
      mapCommand,
      sendMapCommand,
      refreshKey,
      refresh,
      stream,
      pipeline,
      toasts,
      pushToast,
      dismissToast,
      browserNotify,
      setBrowserNotify,
    ],
  );
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
