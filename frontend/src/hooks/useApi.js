import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client.js';
import { useApp } from '../state/AppContext.jsx';

/**
 * Fetch an API resource and keep it fresh.
 *
 * - Re-fetches when `path`/`params` change, when the live stream signals new data
 *   (refreshKey from AppContext), and optionally on an interval.
 * - Keeps the previous data while refreshing so panels never flash empty.
 * - `enabled=false` skips the request entirely.
 */
export function useApi(path, params = null, { enabled = true, interval = 0, live = true } = {}) {
  const { refreshKey } = useApp();
  const [state, setState] = useState({ data: null, meta: null, error: null, loading: enabled, refreshing: false });
  const [manual, setManual] = useState(0);
  const paramsKey = JSON.stringify(params || {});
  const hasData = useRef(false);

  const reload = useCallback(() => setManual((n) => n + 1), []);

  useEffect(() => {
    if (!enabled || !path) {
      setState((s) => ({ ...s, loading: false, refreshing: false }));
      return undefined;
    }
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: !hasData.current, refreshing: hasData.current }));
    api
      .get(path, JSON.parse(paramsKey), controller.signal)
      .then(({ data, meta }) => {
        hasData.current = true;
        setState({ data, meta, error: null, loading: false, refreshing: false });
      })
      .catch((error) => {
        if (error.name === 'AbortError') return;
        setState((s) => ({ ...s, error, loading: false, refreshing: false }));
      });
    return () => controller.abort();
  }, [path, paramsKey, enabled, manual, live ? refreshKey : 0]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!interval || !enabled) return undefined;
    const id = window.setInterval(reload, interval);
    return () => window.clearInterval(id);
  }, [interval, enabled, reload]);

  return { ...state, reload };
}
