import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, Factory, MapPin, Search, Siren } from 'lucide-react';
import { api } from '../../api/client.js';
import { useApp } from '../../state/AppContext.jsx';
import { Spinner } from '../common/ui.jsx';
import s from './GlobalSearch.module.css';

const GROUPS = [
  { key: 'incidents', label: 'Incidents', icon: Siren },
  { key: 'alerts', label: 'Alerts', icon: Bell },
  { key: 'facilities', label: 'Facilities', icon: Factory },
  { key: 'locations', label: 'Locations', icon: MapPin },
];

export default function GlobalSearch() {
  const navigate = useNavigate();
  const { focusMap, setSelection } = useApp();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ loading: false, data: null, error: null });
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const boxRef = useRef(null);

  // Ctrl/Cmd+K focuses search.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    const onDoc = (e) => boxRef.current && !boxRef.current.contains(e.target) && setOpen(false);
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setState({ loading: false, data: null, error: null });
      return undefined;
    }
    const controller = new AbortController();
    const t = window.setTimeout(() => {
      setState((st) => ({ ...st, loading: true }));
      api
        .get('/api/search', { q: term, limit: 5 }, controller.signal)
        .then(({ data }) => {
          setState({ loading: false, data, error: null });
          setActive(0);
        })
        .catch((error) => error.name !== 'AbortError' && setState({ loading: false, data: null, error }));
    }, 350);
    return () => {
      window.clearTimeout(t);
      controller.abort();
    };
  }, [q]);

  const flat = useMemo(() => GROUPS.flatMap((g) => (state.data?.[g.key] || []).map((item) => ({ ...item, group: g.key }))), [state.data]);

  function choose(item) {
    setOpen(false);
    setQ('');
    if (item.kind === 'incident') navigate(`/investigation/${item.id}`);
    else if (item.kind === 'alert') navigate(item.incident_id ? `/investigation/${item.incident_id}` : '/alerts');
    else {
      if (item.kind === 'facility') setSelection({ type: 'facility', id: item.id, lon: item.lon, lat: item.lat });
      focusMap(item.lon, item.lat, item.zoom || 11);
      navigate('/dashboard');
    }
  }

  function onKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => Math.min(flat.length - 1, a + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === 'Enter' && flat[active]) {
      e.preventDefault();
      choose(flat[active]);
    } else if (e.key === 'Escape') {
      setOpen(false);
      inputRef.current?.blur();
    }
  }

  const showPanel = open && q.trim().length >= 2;
  let index = -1;
  return (
    <div className={s.wrap} ref={boxRef}>
      <Search size={15} className={s.icon} />
      <input
        ref={inputRef}
        className={s.input}
        type="search"
        placeholder="Search facilities, incidents, alerts, places…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        aria-label="Search"
        aria-expanded={showPanel}
        aria-controls="global-search-results"
        role="combobox"
      />
      <kbd className={s.kbd}>Ctrl K</kbd>
      {showPanel && (
        <div className={s.panel} id="global-search-results" role="listbox">
          {state.loading && !state.data && (
            <div className={s.status}>
              <Spinner /> Searching…
            </div>
          )}
          {state.error && <div className={s.status}>{state.error.message}</div>}
          {state.data && flat.length === 0 && !state.loading && <div className={s.status}>No matches for “{q.trim()}”.</div>}
          {GROUPS.map((g) => {
            const items = state.data?.[g.key] || [];
            if (!items.length) return null;
            return (
              <div key={g.key} className={s.group}>
                <div className={s.groupLabel}>{g.label}</div>
                {items.map((item) => {
                  index += 1;
                  const i = index;
                  return (
                    <button
                      key={`${g.key}-${item.id ?? item.label}`}
                      type="button"
                      role="option"
                      aria-selected={i === active}
                      className={s.item}
                      onMouseEnter={() => setActive(i)}
                      onClick={() => choose(item)}
                    >
                      <g.icon size={14} className={s.itemIcon} />
                      <span className={s.itemText}>
                        <span className={s.itemLabel}>{item.label}</span>
                        <span className={s.itemDetail}>{item.detail}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
