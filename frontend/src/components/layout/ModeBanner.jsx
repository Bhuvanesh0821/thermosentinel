import { FlaskConical } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useApi } from '../../hooks/useApi.js';
import s from './ModeBanner.module.css';

/** Persistent, unmissable notice whenever the API serves the labelled test fixture instead of live data. */
export default function ModeBanner() {
  const health = useApi('/api/health', null, { interval: 60000, live: false });
  if (health.data?.data_mode !== 'test-fixture') return null;
  return (
    <div className={s.banner} role="status">
      <FlaskConical size={15} />
      <strong>TEST MODE</strong>
      <span>
        Replayed, labelled FIRMS fixture on a separate test database - not live data. Facilities named "TEST FIXTURE" are not real
        sites.
      </span>
      <Link to="/settings?tab=sources">Details</Link>
    </div>
  );
}
