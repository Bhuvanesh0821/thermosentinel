import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { FACILITY_GROUPS, FRP_STOPS, PRIORITY, PRIORITY_ORDER } from '../../utils/constants.js';
import s from './Map.module.css';

export default function MapLegend({ layers, landCoverClasses }) {
  // Collapsed by default on phones so the map stays visible.
  const [open, setOpen] = useState(() => typeof window === 'undefined' || window.innerWidth > 760);
  return (
    <div className={`${s.floating} ${s.legend}`}>
      <button type="button" className={s.floatingHead} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>Legend</span>
        <ChevronDown size={14} className={s.chev} />
      </button>
      {open && (
        <div className={s.legendBody}>
          <div className={s.legendBlock}>
            <div className={s.legendTitle}>Monitoring area</div>
            <span className={s.legendItem}>
              <span className={s.legendLine} style={{ borderTopColor: '#1F2A3D' }} />
              India boundary (official)
            </span>
            <span className={s.legendItem}>
              <span className={s.legendLine} style={{ borderTopColor: '#5B7FD6', borderTopStyle: 'dashed' }} />
              Exclusive Economic Zone
            </span>
          </div>
          {(layers.hotspots || layers.heat) && (
            <div className={s.legendBlock}>
              <div className={s.legendTitle}>Fire radiative power (MW)</div>
              <div className={s.ramp} style={{ background: `linear-gradient(90deg, ${FRP_STOPS.map(([, c]) => c).join(',')})` }} />
              <div className={s.rampLabels}>
                {FRP_STOPS.map(([v]) => (
                  <span key={v} className="mono">
                    {v}
                    {v === FRP_STOPS[FRP_STOPS.length - 1][0] ? '+' : ''}
                  </span>
                ))}
              </div>
            </div>
          )}
          {(layers.clusters || layers.incidents || layers.riskzones) && (
            <div className={s.legendBlock}>
              <div className={s.legendTitle}>Priority (clusters, incidents, zones)</div>
              <div className={s.legendRow}>
                {PRIORITY_ORDER.map((p) => (
                  <span key={p} className={s.legendItem}>
                    <span className={s.legendDot} style={{ background: PRIORITY[p].color }} />
                    {PRIORITY[p].label}
                  </span>
                ))}
              </div>
            </div>
          )}
          {layers.facilities && (
            <div className={s.legendBlock}>
              <div className={s.legendTitle}>Industrial facilities</div>
              <div className={s.legendGrid}>
                {Object.entries(FACILITY_GROUPS).map(([key, g]) => (
                  <span key={key} className={s.legendItem}>
                    <span className={s.legendDot} style={{ background: g.color, boxShadow: '0 0 0 1.5px #fff, 0 0 0 2.5px rgba(0,0,0,.08)' }} />
                    {g.label}
                  </span>
                ))}
              </div>
            </div>
          )}
          {layers.landcover && landCoverClasses.length > 0 && (
            <div className={s.legendBlock}>
              <div className={s.legendTitle}>ESA WorldCover 2021</div>
              <div className={s.legendGrid}>
                {landCoverClasses.map((c) => (
                  <span key={c.code} className={s.legendItem}>
                    <span className={s.legendSquare} style={{ background: c.color }} />
                    {c.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
