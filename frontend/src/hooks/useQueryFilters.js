import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { DEFAULT_FILTERS, useApp } from '../state/AppContext.jsx';

const LIST = (v) => (v ? v.split(',').filter(Boolean) : []);

/**
 * Applies filter parameters present in the URL (e.g. from a voice command or a shared link:
 * /incidents?min_priority=high&facility_type=refinery) to the shared filter state.
 */
export function useQueryFilters() {
  const { search } = useLocation();
  const { setFilters } = useApp();
  useEffect(() => {
    const q = new URLSearchParams(search);
    if (![...q.keys()].length) return;
    const next = {};
    if (q.has('hours')) next.hours = Number(q.get('hours')) || DEFAULT_FILTERS.hours;
    if (q.has('min_priority')) next.minPriority = q.get('min_priority') || null;
    if (q.has('classification')) next.classification = LIST(q.get('classification'));
    if (q.has('facility_type')) next.facilityType = LIST(q.get('facility_type'));
    if (q.has('persistence')) next.persistence = LIST(q.get('persistence'));
    if (q.has('confidence')) next.confidence = q.get('confidence') || null;
    if (Object.keys(next).length) {
      // A command/link defines the whole filter state it cares about.
      setFilters((f) => ({ ...f, minPriority: null, classification: [], facilityType: [], persistence: [], ...next }));
    }
  }, [search, setFilters]);
}
