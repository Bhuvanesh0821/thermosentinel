import { useState } from 'react';
import { AlertCircle, ChevronDown, Layers } from 'lucide-react';
import { FACILITY_GROUPS, PRIORITY } from '../../utils/constants.js';
import { fmtInt } from '../../utils/format.js';
import { Spinner } from '../common/ui.jsx';
import s from './Map.module.css';

const LAYER_META = [
  { id: 'hotspots', label: 'Thermal detections', swatch: 'linear-gradient(90deg,#FCD34D,#EA580C,#7F1D1D)', source: 'NASA FIRMS' },
  { id: 'clusters', label: 'Thermal clusters', swatch: `radial-gradient(circle, transparent 45%, ${PRIORITY.high.color} 48%)`, source: 'ST-DBSCAN' },
  { id: 'incidents', label: 'Incidents', swatch: PRIORITY.critical.color, source: 'Intelligence engine' },
  { id: 'riskzones', label: 'Risk zones', swatch: `repeating-linear-gradient(45deg, ${PRIORITY.high.soft}, ${PRIORITY.high.soft} 3px, ${PRIORITY.high.color} 3px, ${PRIORITY.high.color} 4px)`, source: 'Association buffers' },
  { id: 'facilities', label: 'Industrial facilities', swatch: FACILITY_GROUPS.hydrocarbon.color, source: 'OpenStreetMap' },
  { id: 'footprints', label: 'Facility outlines', swatch: `linear-gradient(135deg, ${FACILITY_GROUPS.hydrocarbon.color}33, ${FACILITY_GROUPS.hydrocarbon.color}66)`, source: 'OpenStreetMap' },
  { id: 'landcover', label: 'Land-cover samples', swatch: 'conic-gradient(#F096FF 0 25%, #FA0000 0 50%, #006400 0 75%, #B4B4B4 0)', source: 'ESA WorldCover' },
  { id: 'heat', label: 'Detection density', swatch: 'radial-gradient(circle,#991B1B,#FB923C 55%,#FCD34D00 75%)', source: 'NASA FIRMS' },
];

function countOf(state) {
  if (!state) return null;
  if (state.meta?.total !== undefined) return state.meta.total;
  if (state.meta?.count !== undefined) return state.meta.count;
  if (state.data?.features) return state.data.features.length;
  return null;
}

export default function LayerPanel({ layers, setLayers, basemap, setBasemap, basemaps, states }) {
  // Collapsed by default on phones so the map stays visible.
  const [open, setOpen] = useState(() => typeof window === 'undefined' || window.innerWidth > 760);
  return (
    <div className={`${s.floating} ${s.layerPanel}`} data-open={open}>
      <button type="button" className={s.floatingHead} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Layers size={15} />
        <span>Layers</span>
        <ChevronDown size={14} className={s.chev} />
      </button>
      {open && (
        <div className={s.layerBody}>
          <ul className={s.layerList}>
            {LAYER_META.map((meta) => {
              const st = states[meta.id];
              const enabled = layers[meta.id];
              const count = countOf(st);
              return (
                <li key={meta.id}>
                  <label className={s.layerRow} title={`Source: ${meta.source}`}>
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={(e) => setLayers((l) => ({ ...l, [meta.id]: e.target.checked }))}
                    />
                    <span className={s.swatch} style={{ background: meta.swatch }} />
                    <span className={s.layerLabel}>{meta.label}</span>
                    <span className={s.layerCount}>
                      {enabled && st?.loading && <Spinner label={`Loading ${meta.label}`} />}
                      {enabled && !st?.loading && st?.error && (
                        <AlertCircle size={13} color="var(--err)" aria-label={st.error.message}>
                          <title>{st.error.message}</title>
                        </AlertCircle>
                      )}
                      {enabled && !st?.loading && !st?.error && st?.note && <span className={s.note}>{st.note}</span>}
                      {enabled && !st?.loading && !st?.error && !st?.note && count !== null && meta.id !== 'heat' && (
                        <span className="mono">{fmtInt(count)}</span>
                      )}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
          <div className={s.basemaps}>
            <div className={s.basemapLabel}>Basemap</div>
            <div className={s.basemapGrid}>
              {basemaps.map((b) => (
                <button key={b.id} type="button" className={s.basemapBtn} aria-pressed={basemap === b.id} onClick={() => setBasemap(b.id)} title={b.attribution}>
                  {b.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
