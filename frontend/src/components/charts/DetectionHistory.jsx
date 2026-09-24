import { useMemo, useState } from 'react';
import { useElementWidth } from '../../hooks/useElementWidth.js';
import { fmtNum, fmtUtc, titleCase } from '../../utils/format.js';
import Tooltip from './Tooltip.jsx';
import s from './chart.module.css';

const HEIGHT = 150;
const M = { top: 8, right: 10, bottom: 22, left: 34 };
const HIT_RADIUS = 14; // >= 24px hit target around each 8px marker

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v);
}

const DAY_MS = 86_400_000;
const shortDate = (t) => new Date(t).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' });
const shortTime = (t) => new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' });

/**
 * FRP of every member detection over time. Single series (series-1 hue); day vs night is
 * a shape encoding (filled vs hollow marker), so identity never relies on colour. The
 * detections table below the chart is its table view.
 */
export default function DetectionHistory({ observations }) {
  const [ref, width] = useElementWidth();
  const [active, setActive] = useState(null);

  const points = useMemo(
    () =>
      (observations || [])
        .filter((o) => o.frp != null)
        .map((o) => ({ ...o, t: new Date(o.acquired_at).getTime() }))
        .sort((a, b) => a.t - b.t),
    [observations],
  );

  if (!points.length) {
    return <div className={s.muted}>No FRP values reported for these detections.</div>;
  }

  let t0 = points[0].t;
  let t1 = points[points.length - 1].t;
  if (t1 - t0 < 6 * 3600_000) {
    const mid = (t0 + t1) / 2;
    t0 = mid - 12 * 3600_000;
    t1 = mid + 12 * 3600_000;
  }
  const pad = (t1 - t0) * 0.04;
  t0 -= pad;
  t1 += pad;
  const yMax = niceMax(Math.max(...points.map((p) => p.frp)));
  const plotW = Math.max(0, width - M.left - M.right);
  const plotH = HEIGHT - M.top - M.bottom;
  const x = (t) => M.left + ((t - t0) / (t1 - t0)) * plotW;
  const y = (v) => M.top + plotH - (v / yMax) * plotH;
  const yTicks = [0, yMax / 2, yMax];

  const span = t1 - t0;
  const xTickCount = Math.max(2, Math.min(5, Math.floor(plotW / 80)));
  const xTicks = Array.from({ length: xTickCount }, (_, i) => t0 + ((i + 0.5) * span) / xTickCount);
  const fmtX = span > 2 * DAY_MS ? shortDate : (t) => `${shortDate(t)} ${shortTime(t)}`;

  const nearest = (px, py) => {
    let best = null;
    let bestD = Infinity;
    points.forEach((p, i) => {
      const d = Math.hypot(x(p.t) - px, y(p.frp) - py);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    return bestD <= HIT_RADIUS ? best : null;
  };

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setActive(nearest(e.clientX - rect.left, e.clientY - rect.top));
  };
  const onKey = (e) => {
    if (e.key === 'ArrowRight') setActive((a) => Math.min(points.length - 1, (a ?? -1) + 1));
    else if (e.key === 'ArrowLeft') setActive((a) => Math.max(0, (a ?? points.length) - 1));
    else if (e.key === 'Escape') setActive(null);
    else return;
    e.preventDefault();
  };

  const p = active !== null ? points[active] : null;
  return (
    <div>
      <div className={s.legend} aria-hidden="true">
        <span className={s.legendItem}>
          <svg width="10" height="10">
            <circle cx="5" cy="5" r="4" fill="var(--chart-series-1)" />
          </svg>
          Day detection
        </span>
        <span className={s.legendItem}>
          <svg width="10" height="10">
            <circle cx="5" cy="5" r="3.2" fill="var(--surface)" stroke="var(--chart-series-1)" strokeWidth="1.8" />
          </svg>
          Night detection
        </span>
        <span className={s.legendItem} style={{ marginLeft: 'auto', color: 'var(--text-3)' }}>
          FRP (MW)
        </span>
      </div>
      <div ref={ref} className={s.root} style={{ height: HEIGHT }}>
        {width > 0 && (
          <svg
            className={s.svg}
            width={width}
            height={HEIGHT}
            role="img"
            aria-label={`Fire radiative power of ${points.length} detections between ${fmtUtc(points[0].acquired_at)} and ${fmtUtc(points[points.length - 1].acquired_at)}`}
            tabIndex={0}
            onPointerMove={onMove}
            onPointerLeave={() => setActive(null)}
            onKeyDown={onKey}
            onBlur={() => setActive(null)}
          >
            {yTicks.map((v) => (
              <g key={v}>
                <line className={v === 0 ? s.baseline : s.gridline} x1={M.left} x2={M.left + plotW} y1={Math.round(y(v)) + 0.5} y2={Math.round(y(v)) + 0.5} />
                <text className={s.tick} x={M.left - 6} y={y(v) + 3} textAnchor="end">
                  {fmtNum(v, v < 10 && v % 1 ? 1 : 0)}
                </text>
              </g>
            ))}
            {xTicks.map((t) => (
              <text key={t} className={s.tick} x={x(t)} y={HEIGHT - 6} textAnchor="middle">
                {fmtX(t)}
              </text>
            ))}
            {p && <line className={s.crosshair} x1={Math.round(x(p.t)) + 0.5} x2={Math.round(x(p.t)) + 0.5} y1={M.top} y2={M.top + plotH} />}
            {points.map((pt, i) => {
              const night = pt.daynight === 'N';
              return (
                <circle
                  key={pt.id}
                  cx={x(pt.t)}
                  cy={y(pt.frp)}
                  r={active === i ? 5.5 : 4}
                  fill={night ? 'var(--surface)' : 'var(--chart-series-1)'}
                  stroke={night ? 'var(--chart-series-1)' : 'var(--surface)'}
                  strokeWidth={night ? 1.8 : 2}
                />
              );
            })}
          </svg>
        )}
        {p && (
          <Tooltip
            x={Math.min(Math.max(x(p.t), 80), width - 80)}
            y={y(p.frp)}
            title={fmtUtc(p.acquired_at)}
            value={`${fmtNum(p.frp)} MW`}
            rows={[
              { label: 'Satellite', value: p.satellite_name || '—' },
              { label: 'Confidence', value: p.confidence_pct != null ? `${p.confidence_pct}%` : titleCase(p.confidence_level || '—') },
              { label: 'Pass', value: p.daynight === 'N' ? 'Night' : 'Day' },
            ]}
          />
        )}
      </div>
    </div>
  );
}
