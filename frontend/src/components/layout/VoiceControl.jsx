import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, CornerDownLeft, Mic, MicOff, Volume2, VolumeX, X } from 'lucide-react';
import { api } from '../../api/client.js';
import { useApp } from '../../state/AppContext.jsx';
import { Spinner } from '../common/ui.jsx';
import s from './VoiceControl.module.css';

const Recognition = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

function speak(text, enabled) {
  if (!enabled || !text || !('speechSynthesis' in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'en-IN';
  u.rate = 1.03;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

/**
 * Voice + typed command control. Speech-to-text runs in the browser (Web Speech API); the
 * transcript is interpreted by the backend into one whitelisted action. The interpreted
 * command is always shown, and unsupported commands are reported - never faked.
 */
export default function VoiceControl() {
  const navigate = useNavigate();
  const { focusMap, setSelection } = useApp();
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState('idle'); // idle | listening | interpreting | done | error
  const [transcript, setTranscript] = useState('');
  const [typed, setTyped] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [voiceOut, setVoiceOut] = useState(true);
  const recRef = useRef(null);
  const boxRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => boxRef.current && !boxRef.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  useEffect(() => () => recRef.current?.abort?.(), []);

  function execute(r) {
    if (!r?.supported || !r.action) return;
    const a = r.action;
    if (a.type === 'navigate') navigate(a.path);
    if (a.type === 'focus') {
      if (a.cluster_id) setSelection({ type: 'cluster', id: a.cluster_id, incidentId: a.incident_id });
      focusMap(a.lon, a.lat, a.zoom || 11);
      navigate(a.path || '/dashboard');
    }
  }

  async function run(text) {
    const t = text.trim();
    if (!t) return;
    setTranscript(t);
    setPhase('interpreting');
    setError(null);
    try {
      const { data } = await api.post('/api/voice/interpret', null, { text: t });
      setResult(data);
      setPhase('done');
      execute(data);
      speak(data.answer || (data.supported ? data.interpreted_as : 'That command is not supported.'), voiceOut);
    } catch (e) {
      setError(e.message);
      setPhase('error');
    }
  }

  function listen() {
    setOpen(true);
    setResult(null);
    setError(null);
    if (!Recognition) {
      setPhase('idle');
      setError('Speech recognition is not available in this browser - type the command instead.');
      return;
    }
    if (phase === 'listening') {
      recRef.current?.stop();
      return;
    }
    const rec = new Recognition();
    rec.lang = 'en-IN';
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    let finalText = '';
    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      setTranscript((finalText || interim).trim());
    };
    rec.onerror = (e) => {
      setPhase('error');
      setError(
        e.error === 'not-allowed' || e.error === 'service-not-allowed'
          ? 'Microphone access was blocked. Allow the microphone for this site or type the command.'
          : e.error === 'no-speech'
            ? 'No speech was detected. Try again or type the command.'
            : `Speech recognition error: ${e.error}`,
      );
    };
    rec.onend = () => {
      recRef.current = null;
      if (finalText.trim()) run(finalText);
      else setPhase((p) => (p === 'listening' ? 'idle' : p));
    };
    recRef.current = rec;
    setTranscript('');
    setPhase('listening');
    rec.start();
  }

  const listening = phase === 'listening';
  return (
    <div className={s.wrap} ref={boxRef}>
      <button
        type="button"
        className={s.mic}
        data-listening={listening}
        onClick={listen}
        aria-label={listening ? 'Stop listening' : 'Voice command'}
        title={Recognition ? 'Voice command (speak a request)' : 'Command (speech not supported in this browser)'}
      >
        {listening ? <MicOff size={16} /> : <Mic size={16} />}
        <span className={s.micLabel}>{listening ? 'Listening…' : 'Voice'}</span>
      </button>
      {open && (
        <div className={s.panel} role="dialog" aria-label="Voice and command control">
          <header className={s.head}>
            <span className={s.title}>Voice &amp; command</span>
            <button type="button" className={s.iconBtn} onClick={() => setVoiceOut((v) => !v)} title={voiceOut ? 'Mute spoken answers' : 'Speak answers'}>
              {voiceOut ? <Volume2 size={15} /> : <VolumeX size={15} />}
            </button>
            <button type="button" className={s.iconBtn} onClick={() => setOpen(false)} aria-label="Close">
              <X size={15} />
            </button>
          </header>

          <form
            className={s.form}
            onSubmit={(e) => {
              e.preventDefault();
              run(typed);
              setTyped('');
            }}
          >
            <input className={s.input} value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type a command, e.g. Show incidents near refineries" aria-label="Command" />
            <button type="submit" className={s.send} disabled={!typed.trim()} aria-label="Run command">
              <CornerDownLeft size={15} />
            </button>
          </form>

          <div className={s.body}>
            {listening && (
              <div className={s.listening}>
                <span className={s.pulse} /> Listening… {transcript && <em>“{transcript}”</em>}
              </div>
            )}
            {phase === 'interpreting' && (
              <div className={s.row}>
                <Spinner /> Interpreting “{transcript}”…
              </div>
            )}
            {error && (
              <div className={s.errorRow}>
                <AlertTriangle size={14} /> {error}
              </div>
            )}
            {phase === 'done' && result && (
              <div className={s.result}>
                <div className={s.heard}>
                  Heard: <b>“{transcript}”</b>
                </div>
                <div className={s.interp} data-supported={result.supported}>
                  {result.supported ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
                  <span>
                    <span className={s.interpLabel}>{result.supported ? 'Interpreted as' : 'Not executed'}</span>
                    {result.interpreted_as}
                  </span>
                </div>
                {result.supported && result.action && (
                  <div className={s.executed}>
                    {result.action.type === 'navigate' ? `Opened ${result.action.path}` : `Map centred on ${result.action.lat?.toFixed(3)}, ${result.action.lon?.toFixed(3)}`}
                  </div>
                )}
                {result.answer && <p className={s.answer}>{result.answer}</p>}
              </div>
            )}
            {(phase === 'idle' || (result && (!result.supported || result.intent === 'help'))) && (
              <div className={s.suggest}>
                <div className={s.suggestLabel}>Try saying</div>
                <div className={s.chips}>
                  {(result?.suggestions?.length ? result.suggestions : [
                    'Show active thermal anomalies',
                    'Show high priority industrial incidents',
                    'How many persistent thermal sources are active?',
                    'Show incidents near power plants',
                    'Open the latest alert',
                    'Zoom to the latest industrial thermal event',
                  ]).map((c) => (
                    <button key={c} type="button" className={s.chip} onClick={() => run(c)}>
                      {c}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <footer className={s.foot}>
            {Recognition ? 'Speech is transcribed by your browser’s speech service; commands run only after interpretation.' : 'This browser has no speech recognition - typed commands work the same way.'}
          </footer>
        </div>
      )}
    </div>
  );
}
