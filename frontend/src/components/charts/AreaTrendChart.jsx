import { useCallback, useId, useMemo, useRef, useState } from 'react';
import { Table2, LineChart } from 'lucide-react';
import { useElementWidth } from '../../hooks/useElementWidth.js';
import { fmtInt } from '../../utils/format.js';
import s from './AreaTrendChart.module.css';

const M = { top: 12, right: 14, bottom: 26, left: 44 };

function niceMax(v) {
  if (!v || v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 1.2, 1.6, 2, 2.4, 3, 4, 5, 6, 8, 10].map((m) => m * p).find((m) => m >= v);
}

/** Monotone cubic interpolation (Fritsch-Carlson): smooth, never overshoots the data. */
function monotonePath(pts) {
  const n = pts.length;
  if (!n) return '';
  if (n === 1) return `M${pts[0][0]},${pts[0][1]}`;
  const dx = [];
  const m = [];
  for (let i = 0; i < n - 1; i += 1) {
    dx.push(pts[i + 1][0] - pts[i][0]);
    m.push((pts[i + 1][1] - pts[i][1]) / (dx[i] || 1));
  }
  const t = [m[0]];
  for (let i = 1; i < n - 1; i += 1) t.push(m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2);
  t.push(m[n - 2]);
  for (let i = 0; i < n - 1; i += 1) {
    if (m[i] === 0) {
      t[i] = 0;
      t[i + 1] = 0;
      continue;
    }
    const a = t[i] / m[i];
    const b = t[i + 1] / m[i];
    const h = a * a + b * b;
    if (h > 9) {
      const k = 3 / Math.sqrt(h);
      t[i] = k * a * m[i];
      t[i + 1] = k * b * m[i];
    }
  }
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < n - 1; i += 1) {
    const c = dx[i] / 3;
    d += `C${(pts[i][0] + c).toFixed(1)},${(pts[i][1] + c * t[i]).toFixed(1)} ${(pts[i + 1][0] - c).toFixed(1)},${(pts[i + 1][1] - c * t[i + 1]).toFixed(1)} ${pts[i + 1][0].toFixed(1)},${pts[i + 1][1].toFixed(1)}`;
  }
  return d;
}

const utc = (v) => new Date(v);
const fmtTick = (v, stepHours) => {
  const d = utc(v);
  const day = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' });
  return stepHours >= 24 ? day : `${day} ${String(d.getUTCHours()).padStart(2, '0')}`;
};
const fmtWhen = (v, stepHours) => {
  const d = utc(v);
  const day = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
  if (stepHours >= 24) return `${day} (UTC)`;
  const h = (x) => String(x).padStart(2, '0');
  const end = new Date(d.getTime() + stepHours * 3600000);
  return `${day}, ${h(d.getUTCHours())}:00-${h(end.getUTCHours())}:00 UTC`;
};

/**
 * Smooth area/line trend with its own time-range control and a scrubbing crosshair: move the
 * mouse or drag a finger across the plot to read every series at that moment. All series share
 * one unit and one axis. Buckets before stored history (`covered === false`) are hatched, never
 * drawn as zero.
 *
 * series: [{ key, label, color, type: 'area' | 'line', dashed? }] - areas are drawn in order
 * (first = back), lines on top.
 */
export default function AreaTrendChart({
  title,
  badge,
  subtitle,
  data,
  series,
  xKey = 'bucket',
  stepHours = 1,
  height = 230,
  unit = 'detections',
  ranges,
  range,
  onRange,
  loading,
  error,
  emptyText = 'No data in this window.',
}) {
  const [ref, width] = useElementWidth();
  const [hover, setHover] = useState(null);
  const [view, setView] = useState('chart');
  const svgRef = useRef(null);
  const holdTimer = useRef(null);
  const gid = useId().replace(/:/g, '');
  const innerW = Math.max(0, width - M.left - M.right);
  const innerH = height - M.top - M.bottom;
  const rows = data || [];

  const yMax = useMemo(() => niceMax(Math.max(0, ...rows.flatMap((d) => series.map((sr) => Number(d[sr.key]) || 0)))), [rows, series]);
  const x = useCallback((i) => (rows.length > 1 ? (i / (rows.length - 1)) * innerW : innerW / 2), [rows.length, innerW]);
  const y = useCallback((v) => innerH - (v / yMax) * innerH, [innerH, yMax]);
  const covered = rows.map((d) => d.covered !== false);
  const firstCovered = covered.indexOf(true);

  const paths = useMemo(() => {
    if (!rows.length || !innerW) return [];
    const start = Math.max(0, firstCovered);
    return series.map((sr) => {
      const pts = rows.slice(start).map((d, j) => [x(start + j), y(Number(d[sr.key]) || 0)]);
      const line = monotonePath(pts);
      const area = pts.length ? `${line}L${pts.at(-1)[0].toFixed(1)},${innerH}L${pts[0][0].toFixed(1)},${innerH}Z` : '';
      return { ...sr, line, area };
    });
  }, [rows, series, innerW, innerH, x, y, firstCovered]);

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax);
  const labelEvery = Math.max(1, Math.ceil(rows.length / Math.max(2, Math.floor(innerW / 96))));

  const indexAt = (clientX) => {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box || !rows.length) return null;
    const px = clientX - box.left - M.left;
    return Math.max(0, Math.min(rows.length - 1, Math.round((px / Math.max(innerW, 1)) * (rows.length - 1))));
  };
  const onMove = (e) => {
    window.clearTimeout(holdTimer.current);
    setHover(indexAt(e.clientX));
  };
  const onLeave = (e) => {
    // Touch: keep the reading visible briefly after the finger lifts.
    if (e.pointerType === 'touch') holdTimer.current = window.setTimeout(() => setHover(null), 2500);
    else setHover(null);
  };
  const onKey = (e) => {
    if (!rows.length) return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault();
      const step = e.key === 'ArrowRight' ? 1 : -1;
      setHover((h) => Math.max(0, Math.min(rows.length - 1, (h ?? (step > 0 ? -1 : rows.length)) + step)));
    } else if (e.key === 'Escape') setHover(null);
  };

  const hv = hover != null ? rows[hover] : null;
  const hx = hover != null ? x(hover) : 0;
  const tipLeft = Math.min(Math.max(M.left + hx, 90), width - 90);

  return (
    <section className={s.card}>
      <header className={s.head}>
        <div className={s.titleWrap}>
          <h2 className={s.title}>{title}</h2>
          {badge && <span className={s.badge}>{badge}</span>}
          {subtitle && <span className={s.sub}>{subtitle}</span>}
        </div>
        <div className={s.controls}>
          {ranges && (
            <div className={s.ranges} role="group" aria-label="Time range">
              {ranges.map((r) => (
                <button key={r.value} type="button" className={s.range} aria-pressed={r.value === range} onClick={() => onRange(r.value)}>
                  {r.label}
                </button>
              ))}
            </div>
          )}
          <button
            type="button"
            className={s.viewBtn}
            onClick={() => setView(view === 'chart' ? 'table' : 'chart')}
            aria-label={view === 'chart' ? 'Show as table' : 'Show as chart'}
            title={view === 'chart' ? 'Show as table' : 'Show as chart'}
          >
            {view === 'chart' ? <Table2 size={15} /> : <LineChart size={15} />}
          </button>
        </div>
      </header>

      <div className={s.legend}>
        {series.map((sr) => (
          <span key={sr.key} className={s.legendItem}>
            <span className={s.swatch} data-type={sr.type} data-dashed={sr.dashed || undefined} style={{ '--c': sr.color }} />
            {sr.label}
          </span>
        ))}
        {rows.some((d) => d.covered === false) && (
          <span className={s.legendItem}>
            <span className={`${s.swatch} ${s.hatch}`} />
            No FIRMS data stored
          </span>
        )}
      </div>

      {error && <p className={s.state}>{error}</p>}
      {!error && loading && !rows.length && <div className={s.skeleton} style={{ height }} />}
      {!error && !loading && !rows.some((d) => series.some((sr) => Number(d[sr.key]) > 0)) && <p className={s.state}>{emptyText}</p>}

      {view === 'table' && rows.length > 0 && (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead>
              <tr>
                <th>Time (UTC)</th>
                {series.map((sr) => (
                  <th key={sr.key} className={s.num}>
                    {sr.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows
                .slice()
                .reverse()
                .map((d) => (
                  <tr key={d[xKey]}>
                    <td className="mono">{fmtWhen(d[xKey], stepHours)}</td>
                    {d.covered === false ? (
                      <td colSpan={series.length} className={s.muted}>
                        No FIRMS data stored
                      </td>
                    ) : (
                      series.map((sr) => (
                        <td key={sr.key} className={`${s.num} mono`}>
                          {fmtInt(d[sr.key])}
                        </td>
                      ))
                    )}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {view === 'chart' && (
        <div className={s.plot} ref={ref} style={{ height }}>
          {width > 0 && rows.length > 0 && (
            <svg
              ref={svgRef}
              className={s.svg}
              width={width}
              height={height}
              role="img"
              aria-label={`${title}: ${series.map((sr) => sr.label).join(', ')}. Use left and right arrow keys to read values.`}
              tabIndex={0}
              onKeyDown={onKey}
              onPointerMove={onMove}
              onPointerDown={onMove}
              onPointerLeave={onLeave}
              onPointerUp={(e) => e.pointerType === 'touch' && onLeave(e)}
              onBlur={() => setHover(null)}
            >
              <defs>
                {paths
                  .filter((p) => p.type === 'area')
                  .map((p) => (
                    <linearGradient key={p.key} id={`${gid}-${p.key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={p.color} stopOpacity="0.30" />
                      <stop offset="100%" stopColor={p.color} stopOpacity="0.03" />
                    </linearGradient>
                  ))}
                <pattern id={`${gid}-nodata`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <line x1="0" y1="0" x2="0" y2="6" stroke="var(--border)" strokeWidth="2" />
                </pattern>
              </defs>
              <g transform={`translate(${M.left},${M.top})`}>
                {firstCovered > 0 && (
                  <rect x={0} y={0} width={x(firstCovered)} height={innerH} fill={`url(#${gid}-nodata)`} opacity="0.7" />
                )}
                {ticks.map((t) => (
                  <g key={t}>
                    <line className={t === 0 ? s.baseline : s.grid} x1={0} x2={innerW} y1={y(t)} y2={y(t)} />
                    <text className={s.tick} x={-8} y={y(t)} dy="0.32em" textAnchor="end">
                      {fmtInt(t)}
                    </text>
                  </g>
                ))}
                {rows.map((d, i) =>
                  i % labelEvery === 0 ? (
                    <text key={d[xKey]} className={s.tick} x={x(i)} y={innerH + 18} textAnchor={i === 0 ? 'start' : 'middle'}>
                      {fmtTick(d[xKey], stepHours)}
                    </text>
                  ) : null,
                )}
                {paths
                  .filter((p) => p.type === 'area')
                  .map((p) => (
                    <g key={p.key}>
                      <path d={p.area} fill={`url(#${gid}-${p.key})`} />
                      <path d={p.line} fill="none" stroke={p.color} strokeWidth="2" strokeLinejoin="round" />
                    </g>
                  ))}
                {paths
                  .filter((p) => p.type === 'line')
                  .map((p) => (
                    <path
                      key={p.key}
                      d={p.line}
                      fill="none"
                      stroke={p.color}
                      strokeWidth="2"
                      strokeDasharray={p.dashed ? '5 4' : undefined}
                      strokeLinecap="round"
                    />
                  ))}
                {hv && (
                  <g className={s.cursor} style={{ transform: `translateX(${hx}px)` }}>
                    <line className={s.crosshair} x1={0} x2={0} y1={0} y2={innerH} />
                    {hv.covered !== false &&
                      series.map((sr) => (
                        <circle
                          key={sr.key}
                          cx={0}
                          cy={y(Number(hv[sr.key]) || 0)}
                          r="4.5"
                          fill={sr.color}
                          stroke="var(--surface)"
                          strokeWidth="2"
                        />
                      ))}
                  </g>
                )}
                <rect x={0} y={0} width={innerW} height={innerH} fill="transparent" />
              </g>
            </svg>
          )}
          {hv && (
            <div className={s.tip} style={{ left: tipLeft }} role="status">
              <div className={s.tipTime}>{fmtWhen(hv[xKey], stepHours)}</div>
              {hv.covered === false ? (
                <div className={s.tipRow}>No FIRMS data stored for this period</div>
              ) : (
                series.map((sr) => (
                  <div key={sr.key} className={s.tipRow}>
                    <span className={s.swatch} data-type={sr.type} data-dashed={sr.dashed || undefined} style={{ '--c': sr.color }} />
                    <span>{sr.label}</span>
                    <b className="mono">{fmtInt(hv[sr.key])}</b>
                  </div>
                ))
              )}
              <div className={s.tipUnit}>{unit}</div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
