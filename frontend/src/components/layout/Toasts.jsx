import { useNavigate } from 'react-router-dom';
import { X } from 'lucide-react';
import { useApp } from '../../state/AppContext.jsx';
import { PRIORITY } from '../../utils/constants.js';
import s from './Toasts.module.css';

const TONE_COLOR = { info: 'var(--accent)', error: 'var(--err)' };

export default function Toasts() {
  const navigate = useNavigate();
  const { toasts, dismissToast } = useApp();
  return (
    <div className={s.stack} aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={s.toast} style={{ '--tone': PRIORITY[t.tone]?.color || TONE_COLOR[t.tone] || 'var(--accent)' }}>
          <div className={s.body}>
            <div className={s.title}>{t.title}</div>
            {t.body && <div className={s.text}>{t.body}</div>}
            {t.link && (
              <button
                type="button"
                className={s.link}
                onClick={() => {
                  navigate(t.link);
                  dismissToast(t.id);
                }}
              >
                Investigate →
              </button>
            )}
          </div>
          <button type="button" className={s.close} aria-label="Dismiss" onClick={() => dismissToast(t.id)}>
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
