import { useEffect, useState } from 'react';
import { fmtCoord } from '../../utils/format.js';
import s from './Map.module.css';

export default function CoordinateReadout({ map }) {
  const [pos, setPos] = useState(null);
  const [zoom, setZoom] = useState(() => map?.getZoom() ?? 0);

  useEffect(() => {
    if (!map) return undefined;
    let frame = 0;
    const onMove = (e) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setPos(e.lngLat));
    };
    const onZoom = () => setZoom(map.getZoom());
    const onOut = () => setPos(null);
    map.on('mousemove', onMove);
    map.on('zoomend', onZoom);
    map.getCanvas().addEventListener('mouseleave', onOut);
    return () => {
      cancelAnimationFrame(frame);
      map.off('mousemove', onMove);
      map.off('zoomend', onZoom);
      map.getCanvas()?.removeEventListener('mouseleave', onOut);
    };
  }, [map]);

  return (
    <div className={s.coords} aria-hidden="true">
      <span className="mono">{pos ? fmtCoord(pos.lat, pos.lng, 4) : '—'}</span>
      <span className={s.coordsZoom}>
        z <span className="mono">{zoom.toFixed(1)}</span>
      </span>
    </div>
  );
}
