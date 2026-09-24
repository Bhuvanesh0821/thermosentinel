import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, CornerDownLeft, Mic, MicOff, Volume2, VolumeX, X } from 'lucide-react';
import { api } from '../../api/client.js';
import { useApi } from '../../hooks/useApi.js';
import { DEFAULT_FILTERS, useApp } from '../../state/AppContext.jsx';
import { Spinner } from '../common/ui.jsx';
import s from './VoiceControl.module.css';

const Recognition = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

const LANGS = [
  { code: 'en', label: 'English', short: 'EN', speech: 'en-IN' },
  { code: 'hi', label: 'हिंदी', short: 'हिं', speech: 'hi-IN' },
  { code: 'ta', label: 'தமிழ்', short: 'த', speech: 'ta-IN' },
];

const UI = {
  en: {
    title: 'Voice & command',
    placeholder: 'Speak or type in your own words - e.g. Show fires in Chennai today',
    heard: 'Heard',
    understood: 'Understood as',
    notRun: 'Not executed',
    entities: 'Understood',
    try: 'Try saying',
    listening: 'Listening…',
    interpreting: 'Understanding',
    blocked: 'Microphone access was blocked. Allow the microphone for this site or type the command.',
    noSpeech: 'No speech was detected. Try again or type the command.',
    noRecognition: 'Speech recognition is not available in this browser - type the command instead.',
    noVoice: 'No English voice is installed on this device - the answer is shown as text.',
    footer:
      'Speech is transcribed by your browser’s speech service; nothing runs until it is understood, and nothing is ever deleted or changed.',
    mute: 'Mute spoken answers',
    unmute: 'Speak answers',
    language: 'Language',
  },
  hi: {
    title: 'आवाज़ व कमांड',
    placeholder: 'अपने शब्दों में बोलें या लिखें - जैसे: आज चेन्नई में आग दिखाओ',
    heard: 'सुना',
    understood: 'समझा गया',
    notRun: 'नहीं चलाया गया',
    entities: 'पहचाना',
    try: 'ऐसे बोलकर देखें',
    listening: 'सुन रहा हूँ…',
    interpreting: 'समझ रहा हूँ',
    blocked: 'माइक्रोफ़ोन की अनुमति नहीं मिली। इस साइट के लिए माइक्रोफ़ोन चालू करें या कमांड लिखें।',
    noSpeech: 'कोई आवाज़ नहीं मिली। फिर से बोलें या कमांड लिखें।',
    noRecognition: 'इस ब्राउज़र में आवाज़ पहचान उपलब्ध नहीं है - कमांड लिखें।',
    noVoice: 'इस डिवाइस पर हिंदी आवाज़ उपलब्ध नहीं है - जवाब लिखित रूप में दिखाया गया है।',
    footer: 'आवाज़ को आपके ब्राउज़र की स्पीच सेवा लिखती है; समझने के बाद ही कमांड चलती है, और कुछ भी हटाया या बदला नहीं जाता।',
    mute: 'बोलकर जवाब बंद करें',
    unmute: 'जवाब बोलकर सुनाएं',
    language: 'भाषा',
  },
  ta: {
    title: 'குரல் & கட்டளை',
    placeholder: 'உங்கள் சொந்த வார்த்தைகளில் பேசவும் அல்லது தட்டச்சு செய்யவும் - எ.கா. இன்று சென்னையில் தீயைக் காட்டு',
    heard: 'கேட்டது',
    understood: 'புரிந்தது',
    notRun: 'செயல்படுத்தப்படவில்லை',
    entities: 'அடையாளம் கண்டது',
    try: 'இப்படிச் சொல்லிப் பாருங்கள்',
    listening: 'கேட்கிறது…',
    interpreting: 'புரிந்துகொள்கிறது',
    blocked: 'மைக்ரோஃபோன் அனுமதி மறுக்கப்பட்டது. இந்தத் தளத்திற்கு மைக்ரோஃபோனை அனுமதிக்கவும் அல்லது தட்டச்சு செய்யவும்.',
    noSpeech: 'குரல் எதுவும் கேட்கவில்லை. மீண்டும் பேசவும் அல்லது தட்டச்சு செய்யவும்.',
    noRecognition: 'இந்த உலாவியில் குரல் அறிதல் இல்லை - கட்டளையைத் தட்டச்சு செய்யவும்.',
    noVoice: 'இந்தச் சாதனத்தில் தமிழ் குரல் இல்லை - பதில் எழுத்தாகக் காட்டப்பட்டுள்ளது.',
    footer: 'உங்கள் உலாவியின் பேச்சு சேவை குரலை எழுத்தாக்குகிறது; புரிந்த பிறகே கட்டளை இயங்கும், எதுவும் நீக்கப்படவோ மாற்றப்படவோ மாட்டாது.',
    mute: 'பதிலைப் பேசுவதை நிறுத்து',
    unmute: 'பதிலைப் பேசு',
    language: 'மொழி',
  },
};

function readLang() {
  try {
    const v = window.localStorage.getItem('ts.voiceLang');
    return LANGS.some((l) => l.code === v) ? v : 'en';
  } catch {
    return 'en';
  }
}

/** A system voice for the language (prefers an Indian English voice for English). */
function pickVoice(code) {
  if (!('speechSynthesis' in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  if (code === 'en') return voices.find((v) => v.lang === 'en-IN') || voices.find((v) => v.lang.startsWith('en')) || null;
  return voices.find((v) => v.lang.toLowerCase().startsWith(code)) || null;
}

/**
 * Voice + typed commands in English, Hindi and Tamil. Speech-to-text runs in the browser (Web
 * Speech API) in the chosen language; the backend understands free-form requests and returns one
 * whitelisted, read-only action plus an answer in the same language, which is spoken back.
 * Unsupported or destructive requests are reported - never faked.
 */
export default function VoiceControl() {
  const navigate = useNavigate();
  const { focusMap, setSelection, setFilters, sendMapCommand } = useApp();
  const [open, setOpen] = useState(false);
  const [lang, setLangState] = useState(readLang);
  const [phase, setPhase] = useState('idle'); // idle | listening | interpreting | done | error
  const [transcript, setTranscript] = useState('');
  const [typed, setTyped] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [voiceNote, setVoiceNote] = useState(null);
  const [voiceOut, setVoiceOut] = useState(true);
  const recRef = useRef(null);
  const boxRef = useRef(null);
  const examples = useApi('/api/voice/commands', { lang }, { live: false });
  const t = UI[lang];
  const langMeta = LANGS.find((l) => l.code === lang);

  function setLang(code) {
    setLangState(code);
    setResult(null);
    setError(null);
    setVoiceNote(null);
    try {
      window.localStorage.setItem('ts.voiceLang', code);
    } catch {
      /* preference lasts for this session only */
    }
  }

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
  // Voices load asynchronously in some browsers.
  useEffect(() => {
    if ('speechSynthesis' in window) window.speechSynthesis.getVoices();
  }, []);

  function speak(textToSay, code) {
    setVoiceNote(null);
    if (!voiceOut || !textToSay || !('speechSynthesis' in window)) return;
    const voice = pickVoice(code);
    if (!voice && code !== 'en') {
      setVoiceNote(UI[code].noVoice);
      return;
    }
    const u = new SpeechSynthesisUtterance(textToSay);
    u.lang = LANGS.find((l) => l.code === code)?.speech || 'en-IN';
    if (voice) u.voice = voice;
    u.rate = 1.02;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }

  function execute(r) {
    if (!r?.supported || !r.action) return;
    const a = r.action;
    if (a.type === 'navigate') {
      navigate(a.path);
      return;
    }
    if (a.type === 'focus') {
      if (a.cluster_id) setSelection({ type: 'cluster', id: a.cluster_id, incidentId: a.incident_id });
      focusMap(a.lon, a.lat, a.zoom || 11);
      navigate(a.path || '/dashboard');
      return;
    }
    if (a.type !== 'apply') return;
    if (a.reset) setFilters(DEFAULT_FILTERS);
    // A spoken request describes the whole view it wants, so it starts from the default filters.
    if (a.filters) setFilters({ ...DEFAULT_FILTERS, ...a.filters });
    if (a.basemap || a.layers) sendMapCommand({ basemap: a.basemap, layers: a.layers });
    if (a.selection) setSelection(a.selection);
    if (a.focus) focusMap(a.focus.lon, a.focus.lat, a.focus.zoom || 11, a.focus.bbox || null);
    if (a.path) navigate(a.path);
  }

  async function run(textToRun) {
    const q = textToRun.trim();
    if (!q) return;
    setTranscript(q);
    setPhase('interpreting');
    setError(null);
    try {
      const { data } = await api.post('/api/voice/interpret', null, { text: q, lang });
      setResult(data);
      setPhase('done');
      execute(data);
      speak(data.answer || data.interpreted_as, data.lang || lang);
    } catch (e) {
      setError(e.message);
      setPhase('error');
    }
  }

  function listen() {
    setOpen(true);
    setResult(null);
    setError(null);
    setVoiceNote(null);
    if (!Recognition) {
      setPhase('idle');
      setError(t.noRecognition);
      return;
    }
    if (phase === 'listening') {
      recRef.current?.stop();
      return;
    }
    const rec = new Recognition();
    rec.lang = langMeta.speech;
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
          ? t.blocked
          : e.error === 'no-speech'
            ? t.noSpeech
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
  const suggestions = result?.suggestions?.length ? result.suggestions : examples.data || [];
  return (
    <div className={s.wrap} ref={boxRef}>
      <button
        type="button"
        className={s.mic}
        data-listening={listening}
        onClick={listen}
        aria-label={listening ? 'Stop listening' : 'Voice command'}
        title={Recognition ? `Voice command (${langMeta.label})` : 'Command (speech not supported in this browser)'}
      >
        {listening ? <MicOff size={16} /> : <Mic size={16} />}
        <span className={s.micLabel}>{listening ? t.listening : `Voice · ${langMeta.short}`}</span>
      </button>
      {open && (
        <div className={s.panel} role="dialog" aria-label={t.title} lang={lang}>
          <header className={s.head}>
            <span className={s.title}>{t.title}</span>
            <div className={s.langs} role="group" aria-label={t.language}>
              {LANGS.map((l) => (
                <button
                  key={l.code}
                  type="button"
                  className={s.lang}
                  aria-pressed={lang === l.code}
                  onClick={() => setLang(l.code)}
                  lang={l.code}
                >
                  {l.label}
                </button>
              ))}
            </div>
            <button type="button" className={s.iconBtn} onClick={() => setVoiceOut((v) => !v)} title={voiceOut ? t.mute : t.unmute}>
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
            <input
              className={s.input}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={t.placeholder}
              aria-label="Command"
            />
            <button type="submit" className={s.send} disabled={!typed.trim()} aria-label="Run command">
              <CornerDownLeft size={15} />
            </button>
          </form>

          <div className={s.body}>
            {listening && (
              <div className={s.listening}>
                <span className={s.pulse} /> {t.listening} {transcript && <em>“{transcript}”</em>}
              </div>
            )}
            {phase === 'interpreting' && (
              <div className={s.row}>
                <Spinner /> {t.interpreting} “{transcript}”…
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
                  {t.heard}: <b>“{transcript}”</b>
                </div>
                <div className={s.interp} data-supported={result.supported}>
                  {result.supported ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
                  <span>
                    <span className={s.interpLabel}>{result.supported ? t.understood : t.notRun}</span>
                    {result.interpreted_as}
                  </span>
                </div>
                {result.understood?.length > 0 && (
                  <div className={s.entities}>
                    <span className={s.interpLabel}>{t.entities}</span>
                    {result.understood.map((u) => (
                      <span key={u} className={s.entity}>
                        {u}
                      </span>
                    ))}
                  </div>
                )}
                {result.answer && <p className={s.answer}>{result.answer}</p>}
                {voiceNote && <p className={s.note}>{voiceNote}</p>}
              </div>
            )}
            {(phase === 'idle' || (result && (!result.supported || result.intent === 'help'))) && suggestions.length > 0 && (
              <div className={s.suggest}>
                <div className={s.suggestLabel}>{t.try}</div>
                <div className={s.chips}>
                  {suggestions.map((c) => (
                    <button key={c} type="button" className={s.chip} onClick={() => run(c)}>
                      {c}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <footer className={s.foot}>{Recognition ? t.footer : t.noRecognition}</footer>
        </div>
      )}
    </div>
  );
}
