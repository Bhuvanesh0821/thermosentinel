import { useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import s from './MultiSelect.module.css';

/** Compact multi-select: a button showing the selection count, with a checkbox popover. */
export default function MultiSelect({ label, options, value, onChange, swatch }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const toggle = (v) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  const summary = value.length === 0 ? 'All' : value.length === 1 ? options.find((o) => o.value === value[0])?.label || value[0] : `${value.length} selected`;

  return (
    <div className={s.wrap} ref={ref}>
      <button type="button" className={s.button} data-active={value.length > 0} aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className={s.label}>{label}</span>
        <span className={s.summary}>{summary}</span>
        <ChevronDown size={13} />
      </button>
      {open && (
        <div className={s.pop} role="listbox" aria-multiselectable="true" aria-label={label}>
          {options.map((o) => (
            <label key={o.value} className={s.option}>
              <input type="checkbox" checked={value.includes(o.value)} onChange={() => toggle(o.value)} />
              {swatch && o.color && <span className={s.swatch} style={{ background: o.color }} />}
              <span>{o.label}</span>
            </label>
          ))}
          <div className={s.foot}>
            <button type="button" onClick={() => onChange([])} disabled={!value.length}>
              Clear
            </button>
            <button type="button" onClick={() => setOpen(false)}>
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
