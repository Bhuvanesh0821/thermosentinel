// HTML builders for MapLibre popups (values escaped; all content comes from API features).
import { CLASSIFICATION, PRIORITY } from '../../utils/constants.js';
import { escapeHtml as e, fmtCoord, fmtNum, fmtUtc, titleCase } from '../../utils/format.js';

function row(label, value) {
  return `<dt>${e(label)}</dt><dd>${value}</dd>`;
}

export function hotspotPopup(p, lngLat) {
  const conf = p.confidence ? `${titleCase(p.confidence)}${p.confidence_pct != null ? ` (${p.confidence_pct}%)` : ''}` : '—';
  const cls = CLASSIFICATION[p.classification];
  return `
    <div class="ts-pop">
      <div class="ts-pop-kicker">Thermal detection · NASA FIRMS</div>
      <div class="ts-pop-title">FRP ${p.frp != null ? `${fmtNum(p.frp)} MW` : 'not reported'}</div>
      <dl class="ts-pop-kv">
        ${row('Acquired', e(fmtUtc(p.acquired_at)))}
        ${row('Sensor', `${e(p.satellite || '—')} · ${e(p.instrument || '')}`)}
        ${row('Confidence', e(conf))}
        ${row('Brightness', p.brightness != null ? `${fmtNum(p.brightness)} K` : '—')}
        ${row('Day / night', p.daynight === 'N' ? 'Night' : p.daynight === 'D' ? 'Day' : '—')}
        ${row('Location', `<span class="mono">${e(fmtCoord(lngLat.lat, lngLat.lng))}</span>`)}
        ${row('Product', `<span class="mono">${e(p.product)}</span>`)}
      </dl>
      ${
        p.cluster_id
          ? `<div class="ts-pop-foot">${cls ? `<span class="ts-pop-cls" style="--c:${cls.color}">${e(cls.short)}</span>` : ''}
             <button type="button" class="ts-pop-link" data-cluster="${Number(p.cluster_id)}">Open cluster #${Number(p.cluster_id)} →</button></div>`
          : '<div class="ts-pop-foot ts-pop-muted">Not yet clustered (analysis pending)</div>'
      }
    </div>`;
}

export function facilityPopup(p, lngLat) {
  const osm = p.source_ref ? `https://www.openstreetmap.org/${e(p.source_ref)}` : null;
  return `
    <div class="ts-pop">
      <div class="ts-pop-kicker">${e(p.type_label || titleCase(p.type))}</div>
      <div class="ts-pop-title">${e(p.name || 'Unnamed facility')}</div>
      <dl class="ts-pop-kv">
        ${p.operator ? row('Operator', e(p.operator)) : ''}
        ${p.subtype ? row('Detail', e(titleCase(p.subtype))) : ''}
        ${row('Location', `<span class="mono">${e(fmtCoord(lngLat.lat, lngLat.lng))}</span>`)}
        ${row('Outline', p.has_footprint ? 'Mapped (zoom in to view)' : 'Point only')}
      </dl>
      <div class="ts-pop-foot">
        ${osm ? `<a href="${osm}" target="_blank" rel="noreferrer" class="ts-pop-link">OpenStreetMap ${e(p.source_ref)} ↗</a>` : ''}
      </div>
    </div>`;
}

export function landcoverPopup(p) {
  const fractions = typeof p.fractions === 'string' ? JSON.parse(p.fractions) : p.fractions || {};
  const top = Object.entries(fractions)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([code, f]) => `${e(code)}: ${(f * 100).toFixed(0)}%`)
    .join(' · ');
  return `
    <div class="ts-pop">
      <div class="ts-pop-kicker">Land cover · ESA WorldCover 2021</div>
      <div class="ts-pop-title">${e(p.class_name || 'Unknown')} (${((p.fraction || 0) * 100).toFixed(0)}%)</div>
      <dl class="ts-pop-kv">
        ${row('Sample radius', `${Number(p.radius_m) || '—'} m`)}
        ${row('Class codes', `<span class="mono">${top || '—'}</span>`)}
      </dl>
    </div>`;
}

export function clusterTooltip(p) {
  const pr = PRIORITY[p.priority];
  return `
    <div class="ts-pop ts-pop-compact">
      <div class="ts-pop-kicker">Cluster #${Number(p.id)} · ${Number(p.observation_count)} detections</div>
      <div class="ts-pop-title">${e(p.classification_label || 'Not yet analysed')}</div>
      <div class="ts-pop-muted">${pr ? `${e(pr.label)} priority · ` : ''}risk ${p.risk_score != null ? fmtNum(p.risk_score, 0) : '—'}/100</div>
    </div>`;
}
