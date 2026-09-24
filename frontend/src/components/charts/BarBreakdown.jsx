import { fmtInt } from '../../utils/format.js';
import s from './BarBreakdown.module.css';

/**
 * Horizontal bar breakdown of counts (a category -> count list). Every bar carries its label
 * and value as text, so identity never relies on colour; bars with `color` use it only as a
 * redundant cue (e.g. the ordinal priority scale). With `onSelect`, a row is a button that
 * applies that category as a filter; `active` marks the selected one.
 */
export default function BarBreakdown({ rows, onSelect, active, color = '#2a78d6', emptyText = 'No data', unit = '', total: totalOf }) {
  if (!rows.length || rows.every((r) => !r.value)) return <p className={s.empty}>{emptyText}</p>;
  const max = Math.max(1, ...rows.map((r) => r.value || 0));
  // Percentages are of `total` when given (e.g. alerts, where one alert can count in several rows).
  const total = totalOf ?? rows.reduce((a, r) => a + (r.value || 0), 0);
  return (
    <ul className={s.list}>
      {rows.map((r) => {
        const pct = total ? Math.round((100 * (r.value || 0)) / total) : 0;
        const body = (
          <>
            <span className={s.label}>{r.label}</span>
            <span className={s.track} aria-hidden="true">
              {r.value > 0 && (
                <span className={s.fill} style={{ width: `${Math.max(2, (r.value / max) * 100)}%`, background: r.color || color }} />
              )}
            </span>
            <span className={`${s.value} mono`}>
              {fmtInt(r.value)}
              {unit}
            </span>
            <span className={`${s.pct} mono`}>{pct}%</span>
          </>
        );
        const title = `${r.text || r.key}: ${fmtInt(r.value)}${unit} (${pct}%)${onSelect ? (active === r.key ? ' - click to clear' : ' - click to filter') : ''}`;
        return (
          <li key={r.key}>
            {onSelect ? (
              <button
                type="button"
                className={s.row}
                aria-pressed={active === r.key}
                onClick={() => onSelect(active === r.key ? null : r.key)}
                title={title}
                disabled={!r.value && active !== r.key}
              >
                {body}
              </button>
            ) : (
              <div className={s.row} title={title}>
                {body}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
