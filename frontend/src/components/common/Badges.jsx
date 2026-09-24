import { CLASSIFICATION, PERSISTENCE, PRIORITY, STATUS_TONE } from '../../utils/constants.js';
import { titleCase } from '../../utils/format.js';
import { Badge, Dot } from './ui.jsx';

export function PriorityBadge({ priority }) {
  if (!priority) return <Badge tone="idle">Unscored</Badge>;
  return <Badge tone={priority}>{PRIORITY[priority]?.label || priority}</Badge>;
}

export function PersistenceBadge({ category }) {
  if (!category) return null;
  const meta = PERSISTENCE[category] || { label: titleCase(category), tone: 'idle' };
  return (
    <Badge tone={meta.tone} variant={meta.tone === 'idle' ? 'outline' : undefined} title="Temporal persistence at this location">
      {meta.label}
    </Badge>
  );
}

export function ClassificationTag({ classification, short = false }) {
  const meta = CLASSIFICATION[classification];
  if (!meta) return <span style={{ color: 'var(--text-3)' }}>Not yet analysed</span>;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600, color: 'var(--text)' }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: meta.color, flex: 'none' }} />
      {short ? meta.short : meta.label}
    </span>
  );
}

export function StatusBadge({ status }) {
  const tone = STATUS_TONE[status] || 'idle';
  const label = { not_configured: 'Not configured', unknown: 'Awaiting data' }[status] || titleCase(status || 'unknown');
  return (
    <Badge tone={tone} variant={tone === 'idle' ? 'outline' : undefined}>
      <Dot tone={tone} />
      {label}
    </Badge>
  );
}
