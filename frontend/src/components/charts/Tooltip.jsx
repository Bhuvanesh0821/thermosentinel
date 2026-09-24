import s from './chart.module.css';

/** Positioned inside the chart root; content is React-rendered (never raw HTML). */
export default function Tooltip({ x, y, title, value, rows = [] }) {
  return (
    <div className={s.tooltip} style={{ left: x, top: y }} role="status">
      {title && <div className={s.tooltipTitle}>{title}</div>}
      {value && <div className={s.tooltipValue}>{value}</div>}
      {rows.map((row) => (
        <div key={row.label} className={s.tooltipRow}>
          {row.color && <span className={s.key} style={{ background: row.color }} />}
          <span>{row.label}</span>
          <b>{row.value}</b>
        </div>
      ))}
    </div>
  );
}
