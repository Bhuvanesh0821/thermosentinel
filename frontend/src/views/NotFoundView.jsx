import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { EmptyState } from '../components/common/ui.jsx';
import s from './page.module.css';

export default function NotFoundView() {
  return (
    <div className={s.page}>
      <div className={s.card} style={{ maxWidth: 520, margin: '40px auto' }}>
        <EmptyState icon={Compass} title="Page not found" center action={<Link to="/dashboard">Go to the dashboard</Link>}>
          This address does not match any ThermoSentinel view.
        </EmptyState>
      </div>
    </div>
  );
}
