import { AlertTriangle, Database, Inbox, WifiOff } from 'lucide-react';
import s from './ui.module.css';

export function Panel({ title, subtitle, actions, children, className = '', bodyClassName = '', ...rest }) {
  return (
    <section className={`${s.panel} ${className}`} {...rest}>
      {(title || actions) && (
        <header className={s.panelHeader}>
          <div>
            {title && <h2 className={s.panelTitle}>{title}</h2>}
            {subtitle && <div className={s.panelSubtitle}>{subtitle}</div>}
          </div>
          {actions && <div className={s.panelActions}>{actions}</div>}
        </header>
      )}
      <div className={`${s.panelBody} ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function Badge({ tone = 'idle', variant, children, title }) {
  return (
    <span className={s.badge} data-tone={tone} data-variant={variant} title={title}>
      {children}
    </span>
  );
}

export function Dot({ tone = 'idle', pulse = false, title }) {
  return <span className={s.dot} data-tone={tone} data-pulse={pulse} title={title} />;
}

export function Button({ variant, size, icon: Icon, children, className = '', ...rest }) {
  return (
    <button type="button" className={`${s.btn} ${className}`} data-variant={variant} data-size={size} {...rest}>
      {Icon && <Icon size={size === 'sm' ? 13 : 15} strokeWidth={2} />}
      {children}
    </button>
  );
}

export function IconButton({ icon: Icon, label, variant = 'ghost', className = '', ...rest }) {
  return (
    <button type="button" className={`${s.btn} ${s.iconBtn} ${className}`} data-variant={variant} aria-label={label} title={label} {...rest}>
      <Icon size={17} strokeWidth={1.9} />
    </button>
  );
}

export function Segmented({ options, value, onChange, label }) {
  return (
    <div className={s.segmented} role="group" aria-label={label}>
      {options.map((opt) => (
        <button
          key={String(opt.value)}
          type="button"
          className={s.segment}
          aria-pressed={opt.value === value}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function Select({ value, onChange, options, label, ...rest }) {
  return (
    <select
      className={s.select}
      aria-label={label}
      title={label}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
      {...rest}
    >
      {options.map((opt) => (
        <option key={String(opt.value)} value={opt.value ?? ''}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}

export function Spinner({ label = 'Loading' }) {
  return <span className={s.spinner} role="status" aria-label={label} />;
}

export function Skeleton({ width = '100%', height = 12, style }) {
  return <span className={s.skeleton} style={{ width, height, ...style }} />;
}

export function SkeletonRows({ rows = 4, height = 44, gap = 8 }) {
  return (
    <div style={{ display: 'grid', gap }}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} height={height} />
      ))}
    </div>
  );
}

export function EmptyState({ icon: Icon = Inbox, title, children, center = false, action }) {
  return (
    <div className={s.state} data-center={center}>
      <div className={s.stateIcon}>
        <Icon size={17} />
      </div>
      <div className={s.stateTitle}>{title}</div>
      {children && <div className={s.stateBody}>{children}</div>}
      {action}
    </div>
  );
}

/** Map an API error to a user-facing title/body/icon. */
function describeError(error) {
  const code = error?.code;
  let Icon = AlertTriangle;
  let title = 'Could not load data';
  let body = error?.message;
  let tone = 'error';
  if (code === 'database_not_configured') {
    Icon = Database;
    tone = 'warn';
    title = 'Database not connected';
    body = 'Set DATABASE_URL (Neon PostgreSQL) in thermosentinel/.env and restart the API.';
  } else if (code === 'database_unavailable') {
    Icon = Database;
    title = 'Database unreachable';
    body = 'The API is running but cannot reach Neon PostgreSQL. Check the connection string and network.';
  } else if (code === 'network_error') {
    Icon = WifiOff;
    title = 'API unreachable';
    body = 'Cannot reach the ThermoSentinel API. Start the backend (uvicorn) and retry.';
  }
  return { Icon, title, body, tone, code };
}

/** One-line error for dense surfaces (KPI strip, status bars). */
export function InlineError({ error, onRetry }) {
  const { Icon, title, body, tone, code } = describeError(error);
  return (
    <div className={s.inlineError} data-tone={tone} role="alert">
      <Icon size={15} />
      <span className={s.inlineTitle}>{title}</span>
      <span className={s.inlineBody}>{body}</span>
      {code && <span className={s.stateCode}>{code}</span>}
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

/** Renders an API error with guidance specific to the failure. */
export function ErrorState({ error, onRetry, center = false, compact = false }) {
  const { Icon, title, body, tone, code } = describeError(error);
  return (
    <div className={s.state} data-tone={tone} data-center={center} role="alert">
      <div className={s.stateIcon}>
        <Icon size={17} />
      </div>
      <div className={s.stateTitle}>{title}</div>
      {!compact && body && <div className={s.stateBody}>{body}</div>}
      {code && <div className={s.stateCode}>{code}</div>}
      {onRetry && (
        <Button size="sm" onClick={onRetry} style={{ marginTop: 4 }}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function KeyValue({ items }) {
  return (
    <dl className={s.kv}>
      {items
        .filter(Boolean)
        .map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}>
            <dt>{k}</dt>
            <dd>{v ?? '—'}</dd>
          </div>
        ))}
    </dl>
  );
}

export function Meter({ value, color, max = 1, title }) {
  const pct = Math.max(0, Math.min(100, ((value || 0) / max) * 100));
  return (
    <div className={s.meter} title={title}>
      <div className={s.meterFill} style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

export function SectionLabel({ children }) {
  return <h3 className={s.sectionLabel}>{children}</h3>;
}
