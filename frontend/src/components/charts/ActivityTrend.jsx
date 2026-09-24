import { useState } from 'react';
import { useElementWidth } from '../../hooks/useElementWidth.js';
import { fmtInt, fmtUtc } from '../../utils/format.js';
import Tooltip from './Tooltip.jsx';
import s from './chart.module.css';

const GAP = 2; // surface gap between adjacent bars
const MAX_BAR = 24;

function barPath(x, y, w, h, r) {
  // Rounded data-end (top), square at the baseline.
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h} V${y + rr} Q${x},${y} ${x + rr},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h} Z`;
}

/**
 * Compact detections-per-bucket column trend for a KPI tile. Past buckets use the
 * de-emphasis hue, the latest bucket with data the accent. Buckets before stored history
 * began are drawn as a hairline stub ("no data held" in the tooltip), never as zero.
 */
export default function ActivityTrend({ series, height = 34, label }) {
  const [ref, width] = useElementWidth();
  const [active, setActive] = useState(null);
  const buckets = series?.buckets || [];
  const n = buckets.length;
  const max = Math.max(1, ...buckets.map((b) => b.total));
  const lastWithData = buckets.reduce((acc, b, i) => (b.total > 0 ? i : acc), -1);
  const barW = n ? Math.min(MAX_BAR, (width - GAP * (n - 1)) / n) : 0;
  const offset = n ? (width - (barW * n + GAP * (n - 1))) / 2 : 0;
  const xOf = (i) => offset + i * (barW + GAP);

  const pick = (clientX, target) => {
    const rect = target.getBoundingClientRect();
    const i = Math.floor((clientX - rect.left - offset) / (barW + GAP));
    setActive(i >= 0 && i < n ? i : null);
  };

  const onKey = (e) => {
    if (!n) return;
    if (e.key === 'ArrowRight') setActive((a) => Math.min(n - 1, (a ?? -1) + 1));
    else if (e.key === 'ArrowLeft') setActive((a) => Math.max(0, (a ?? n) - 1));
    else if (e.key === 'Escape') setActive(null);
    else return;
    e.preventDefault();
  };

  const b = active !== null ? buckets[active] : null;
  return (
    <div ref={ref} className={s.root} style={{ height }}>
      {width > 0 && n > 0 && (
        <svg
          className={s.svg}
          width={width}
          height={height}
          role="img"
          aria-label={label}
          tabIndex={0}
          onPointerMove={(e) => pick(e.clientX, e.currentTarget)}
          onPointerLeave={() => setActive(null)}
          onKeyDown={onKey}
          onBlur={() => setActive(null)}
        >
          <line className={s.baseline} x1={0} x2={width} y1={height - 0.5} y2={height - 0.5} />
          {buckets.map((bk, i) => {
            const x = xOf(i);
            if (!bk.covered) {
              return <rect key={bk.bucket} x={x} y={height - 2} width={barW} height={1} fill="var(--chart-axis)" />;
            }
            if (bk.total === 0) return null;
            const h = Math.max(2, (bk.total / max) * (height - 3));
            const fill = i === lastWithData ? 'var(--chart-series-1)' : 'var(--chart-muted)';
            return (
              <path
                key={bk.bucket}
                d={barPath(x, height - 1 - h, barW, h, 2)}
                fill={fill}
                opacity={active === null || active === i ? 1 : 0.55}
              />
            );
          })}
        </svg>
      )}
      {b && (
        <Tooltip
          x={Math.min(Math.max(xOf(active) + barW / 2, 70), width - 70)}
          y={0}
          title={`${fmtUtc(b.bucket)} · ${series.bucket}`}
          value={b.covered ? `${fmtInt(b.total)} detections` : 'No data held'}
          rows={
            b.covered && b.total
              ? [
                  { label: 'Day', value: fmtInt(b.day) },
                  { label: 'Night', value: fmtInt(b.night) },
                  { label: 'VIIRS / MODIS', value: `${fmtInt(b.viirs)} / ${fmtInt(b.modis)}` },
                ]
              : []
          }
        />
      )}
    </div>
  );
}
