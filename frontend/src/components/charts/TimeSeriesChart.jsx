import { useMemo, useState } from 'react';
import { useElementWidth } from '../../hooks/useElementWidth.js';
import { fmtInt } from '../../utils/format.js';
import Tooltip from './Tooltip.jsx';
import s from './chart.module.css';

const M = { top: 10, right: 12, bottom: 24, left: 40 };
const GAP = 2; // surface gap between stacked segments

function niceMax(v) {
  if (!v || v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 1.2, 1.6, 2, 2.4, 3, 4, 5, 6, 8, 10].map((m) => m * p).find((m) => m >= v);
}

const dayLabel = (d) => new Date(`${d}T00:00:00Z`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' });

// Bar with only the data end (top) rounded; the baseline end stays square.
function topRoundedBar(x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

/**
 * Daily time series (UTC days). `type="bar"` stacks the series; `type="line"` draws each as a
 * 2px line (gaps where a value is null). Days before the first stored FIRMS detection
 * (`covered === false`) are hatched so "no data" never reads as "zero activity".
 */
export default function TimeSeriesChart({ data, series, type = 'bar', height = 200, unit = '', valueFormat = fmtInt, label }) {
  const [ref, width] = useElementWidth();
  const [hover, setHover] = useState(null);
  const innerW = Math.max(0, width - M.left - M.right);
  const innerH = height - M.top - M.bottom;

  const { yMax, ticks } = useMemo(() => {
    let max = 0;
    data.forEach((d) => {
      if (type === 'bar')
        max = Math.max(
          max,
          series.reduce((acc, sr) => acc + (Number(d[sr.key]) || 0), 0),
        );
      else series.forEach((sr) => (max = Math.max(max, Number(d[sr.key]) || 0)));
    });
    const top = niceMax(max);
    return { yMax: top, ticks: [0, 0.25, 0.5, 0.75, 1].map((f) => f * top) };
  }, [data, series, type]);

  const band = data.length ? innerW / data.length : 0;
  const y = (v) => innerH - (v / yMax) * innerH;
  const xCenter = (i) => i * band + band / 2;
  const barW = Math.max(1, Math.min(22, band * 0.72));
  const labelEvery = Math.max(1, Math.ceil(data.length / Math.max(2, Math.floor(innerW / 64))));

  const lines = useMemo(() => {
    if (type !== 'line') return [];
    return series.map((sr) => {
      let d = '';
      let pen = false;
      data.forEach((row, i) => {
        const v = row[sr.key];
        if (v == null) {
          pen = false;
          return;
        }
        d += `${pen ? 'L' : 'M'}${xCenter(i).toFixed(1)},${y(Number(v)).toFixed(1)}`;
        pen = true;
      });
      return { ...sr, d };
    });
  }, [type, series, data, band, yMax, innerH]); // eslint-disable-line react-hooks/exhaustive-deps

  const hoverRow = hover != null ? data[hover] : null;

  return (
    <div className={s.root} ref={ref}>
      {width > 0 && (
        <svg className={s.svg} width={width} height={height} role="img" aria-label={label}>
          <defs>
            <pattern id="ts-nodata" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="6" stroke="var(--border)" strokeWidth="2" />
            </pattern>
          </defs>
          <g transform={`translate(${M.left},${M.top})`}>
            {data.map((d, i) =>
              d.covered === false ? (
                <rect key={`nd-${d.day}`} x={i * band} y={0} width={band} height={innerH} fill="url(#ts-nodata)" opacity="0.7" />
              ) : null,
            )}
            {ticks.map((t) => (
              <g key={t}>
                {t > 0 && <line className={s.gridline} x1={0} x2={innerW} y1={y(t)} y2={y(t)} />}
                <text className={s.tick} x={-6} y={y(t)} dy="0.32em" textAnchor="end">
                  {valueFormat(t)}
                </text>
              </g>
            ))}
            {hover != null && <line className={s.crosshair} x1={xCenter(hover)} x2={xCenter(hover)} y1={0} y2={innerH} />}
            {type === 'bar' &&
              data.map((d, i) => {
                let acc = 0;
                const segs = series.map((sr) => ({ sr, v: Number(d[sr.key]) || 0 })).filter((p) => p.v > 0);
                return segs.map(({ sr, v }, k) => {
                  const y0 = y(acc);
                  acc += v;
                  const y1 = y(acc);
                  const top = k === segs.length - 1;
                  const h = Math.max(1, y0 - y1 - (k > 0 ? GAP : 0));
                  const x = xCenter(i) - barW / 2;
                  return top ? (
                    <path
                      key={`${d.day}-${sr.key}`}
                      d={topRoundedBar(x, y1, barW, h, 4)}
                      fill={sr.color}
                      opacity={hover == null || hover === i ? 1 : 0.55}
                    />
                  ) : (
                    <rect
                      key={`${d.day}-${sr.key}`}
                      x={x}
                      y={y1}
                      width={barW}
                      height={h}
                      fill={sr.color}
                      opacity={hover == null || hover === i ? 1 : 0.55}
                    />
                  );
                });
              })}
            {lines.map((ln) => (
              <path key={ln.key} d={ln.d} fill="none" stroke={ln.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            ))}
            {type === 'line' &&
              hoverRow &&
              series.map((sr) =>
                hoverRow[sr.key] != null ? (
                  <circle
                    key={sr.key}
                    cx={xCenter(hover)}
                    cy={y(Number(hoverRow[sr.key]))}
                    r="4"
                    fill={sr.color}
                    stroke="var(--surface)"
                    strokeWidth="2"
                  />
                ) : null,
              )}
            <line className={s.baseline} x1={0} x2={innerW} y1={innerH} y2={innerH} />
            {data.map((d, i) =>
              i % labelEvery === 0 ? (
                <text key={`x-${d.day}`} className={s.tick} x={xCenter(i)} y={innerH + 16} textAnchor="middle">
                  {dayLabel(d.day)}
                </text>
              ) : null,
            )}
            {data.map((d, i) => (
              <rect
                key={`hit-${d.day}`}
                x={i * band}
                y={0}
                width={band}
                height={innerH}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
            ))}
          </g>
        </svg>
      )}
      {hoverRow && (
        <Tooltip
          x={Math.min(Math.max(M.left + xCenter(hover), 80), width - 80)}
          y={M.top + 4}
          title={`${dayLabel(hoverRow.day)} ${new Date(`${hoverRow.day}T00:00:00Z`).getUTCFullYear()} (UTC)`}
          value={
            hoverRow.covered === false
              ? 'No FIRMS data stored'
              : type === 'bar'
                ? `${valueFormat(series.reduce((a, sr) => a + (Number(hoverRow[sr.key]) || 0), 0))}${unit ? ` ${unit}` : ''}`
                : undefined
          }
          rows={
            hoverRow.covered === false
              ? []
              : series.map((sr) => ({
                  label: sr.label,
                  color: sr.color,
                  value: hoverRow[sr.key] == null ? '—' : `${valueFormat(Number(hoverRow[sr.key]))}${unit ? ` ${unit}` : ''}`,
                }))
          }
        />
      )}
    </div>
  );
}

export function Legend({ series, noData = false }) {
  return (
    <div className={s.legend}>
      {series.map((sr) => (
        <span key={sr.key} className={s.legendItem}>
          <span className={s.legendSwatch} data-shape={sr.shape || 'box'} style={{ background: sr.color }} />
          {sr.label}
        </span>
      ))}
      {noData && (
        <span className={s.legendItem}>
          <span className={`${s.legendSwatch} ${s.legendHatch}`} />
          No FIRMS data stored
        </span>
      )}
    </div>
  );
}
