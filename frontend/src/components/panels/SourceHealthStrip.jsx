import { useApi } from '../../hooks/useApi.js';
import { useNavigate } from 'react-router-dom';
import { STATUS_TONE } from '../../utils/constants.js';
import { fmtInt, fmtRelative, fmtUtc, titleCase } from '../../utils/format.js';
import { Dot, InlineError, Skeleton } from '../common/ui.jsx';
import s from './SourceHealthStrip.module.css';

// Chips shown on the monitor; related sources are grouped so the strip stays one row.
const GROUPS = [
  { id: 'firms', label: 'NASA FIRMS', members: ['nasa_firms'] },
  { id: 'infra', label: 'Industrial sites', members: ['osm_overpass'] },
  { id: 'landcover', label: 'Land cover', members: ['esa_worldcover'] },
  { id: 'boundary', label: 'India boundary', members: ['ne_india_boundary', 'marineregions_eez'] },
  { id: 'imagery', label: 'Imagery', members: ['nasa_gibs', 'eox_s2cloudless'] },
  { id: 'database', label: 'Database', members: ['database'] },
];

// Worst status wins when a group has several members.
const SEVERITY = ['unavailable', 'degraded', 'not_configured', 'unknown', 'disabled', 'connected'];

const STATUS_LABEL = {
  connected: 'Connected',
  degraded: 'Degraded',
  unavailable: 'Unavailable',
  not_configured: 'Not configured',
  disabled: 'Disabled',
  unknown: 'Awaiting data',
};

function groupDetail(group, members) {
  const [first] = members;
  if (group.id === 'database') {
    return first.latency_ms != null ? `${first.latency_ms} ms round trip` : first.status_message || '';
  }
  if (group.id === 'boundary') return 'Official claim · clipping active';
  if (group.id === 'imagery') return `${members.filter((m) => m.status === 'connected').length}/${members.length} tile services`;
  if (!first.last_success_at) return 'No successful run yet';
  const count = first.last_record_count != null ? ` · ${fmtInt(first.last_record_count)} records` : '';
  return `${fmtRelative(first.last_success_at)}${count}`;
}

function groupTitle(members) {
  return members
    .map(
      (m) =>
        `${m.name}: ${STATUS_LABEL[m.status] || titleCase(m.status)}${m.status_message ? ` — ${m.status_message}` : ''}${
          m.last_success_at ? ` (last success ${fmtUtc(m.last_success_at)})` : ''
        }`,
    )
    .join('\n');
}

export default function SourceHealthStrip() {
  const navigate = useNavigate();
  const { data, error, loading, reload } = useApi('/api/data-sources', null, { interval: 60000 });

  if (error) {
    return (
      <div className={s.strip}>
        <InlineError error={error} onRetry={reload} />
      </div>
    );
  }
  const byId = Object.fromEntries((data || []).map((src) => [src.id, src]));

  return (
    <div className={s.strip} role="list" aria-label="Data source health">
      <button type="button" className={s.heading} onClick={() => navigate('/settings')} title="Open system health & data sources">
        Sources
      </button>
      {GROUPS.map((group) => {
        const members = group.members.map((id) => byId[id]).filter(Boolean);
        if (loading || !members.length) {
          return (
            <div key={group.id} className={s.item}>
              <Skeleton width="70%" height={11} />
              <Skeleton width="50%" height={9} style={{ marginTop: 5 }} />
            </div>
          );
        }
        const status = SEVERITY.find((st) => members.some((m) => m.status === st)) || 'unknown';
        const tone = STATUS_TONE[status] || 'idle';
        return (
          <div key={group.id} className={s.item} role="listitem" title={groupTitle(members)}>
            <div className={s.row}>
              <Dot tone={tone} />
              <span className={s.name}>{group.label}</span>
            </div>
            <div className={s.row}>
              <span className={s.status} data-tone={tone}>
                {STATUS_LABEL[status]}
              </span>
              <span className={s.detail}>{groupDetail(group, members)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
