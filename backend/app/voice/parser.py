"""Free-form command parser (English, Hindi, Tamil and romanised mixes).

`parse(text)` turns any request into a `ParsedCommand`: which verbs were used, what the user
is asking about (detections, incidents, alerts, sources, facilities), filters (priority, event
class, facility type, persistence, day/night, time window), a place from the gazetteer, an
incident/alert number, and any remaining words that may name a place or a facility. It is pure
(no database, no network) so it can be tested exhaustively; `interpreter.py` decides and acts.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.voice import lexicon as L

_NUKTA = "़"
_LATIN = re.compile(r"^[a-z0-9&'-]+$")
_DIGITS = re.compile(r"^\d+$")
_TAMIL = re.compile(r"[஀-௿]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def normalise(text: str) -> str:
    """Lower-case, unify Hindi spellings (nukta, chandrabindu), turn punctuation into spaces.
    Combining vowel signs of Indic scripts are kept (they are part of the word)."""
    t = unicodedata.normalize("NFC", text).lower()
    t = t.replace(_NUKTA, "").replace("ँ", "ं")  # ज़ -> ज, ँ -> ं
    t = t.replace("’", "'").replace("’", "'")
    out = []
    for ch in t:
        cat = unicodedata.category(ch)
        if ch in "&'-":
            out.append(ch)
        elif cat[0] in "PS" or ch in "।॥":
            out.append(" ")
        else:
            out.append(ch)
    t = re.sub(r"\s+", " ", "".join(out)).strip()
    t = t.replace("what's", "what is").replace("whats", "what is")
    return t


def detect_language(text: str) -> str:
    if _TAMIL.search(text):
        return "ta"
    if _DEVANAGARI.search(text):
        return "hi"
    return "en"


def _prep(form: str) -> list[str]:
    return normalise(form).split()


def _word_match(token: str, stem: str) -> bool:
    if token == stem:
        return True
    # Short stems ('in', 'आग', 'தீ') only match whole words; longer ones match inflections too.
    if len(stem) < 3:
        return False
    if token.startswith(stem):
        return True
    # Tamil sandhi: a final consonant (with pulli) fuses with the case ending that follows:
    # ஜார்கண்ட் + இல் -> ஜார்கண்டில், அலர்ட் + ஐ -> அலர்டை.
    return stem.endswith("்") and len(stem) >= 4 and token.startswith(stem[:-1])


@dataclass
class ParsedCommand:
    text: str
    tokens: list[str]
    lang: str
    verbs: set[str] = field(default_factory=set)
    targets: list[str] = field(default_factory=list)
    priority: str | None = None
    classes: list[str] = field(default_factory=list)
    industrial: bool = False
    facility_types: list[str] = field(default_factory=list)
    persistence: str | None = None
    daynight: str | None = None
    hours: int | None = None
    basemap: str | None = None
    page: str | None = None
    place: str | None = None  # canonical gazetteer name
    place_cue: bool = False
    incident_id: int | None = None
    alert_id: int | None = None
    leftover: list[str] = field(default_factory=list)
    leftover_span: str | None = None
    forbidden: bool = False  # asked to delete / change data (refused: the voice interface is read-only)

    @property
    def has_filters(self) -> bool:
        return bool(self.priority or self.classes or self.industrial or self.facility_types or self.persistence
                    or self.daynight or self.hours)


class _Scanner:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.used = [False] * len(tokens)

    def find(self, forms: list[str], consume: bool = True) -> bool:
        """True if any form occurs (longest forms first); consumes the matched tokens."""
        for words in sorted((_prep(f) for f in forms), key=len, reverse=True):
            n = len(words)
            if not n:
                continue
            for i in range(len(self.tokens) - n + 1):
                if any(self.used[i + k] for k in range(n)):
                    continue
                if all(_word_match(self.tokens[i + k], words[k]) for k in range(n)):
                    if consume:
                        for k in range(n):
                            self.used[i + k] = True
                    return True
        return False

    def find_all(self, forms: list[str]) -> bool:
        """Like find(), but consumes every occurrence (e.g. "स्थिति का सारांश" -> both brief words)."""
        found = False
        while self.find(forms):
            found = True
        return found

    def find_key(self, table: dict[str, list[str]]) -> list[str]:
        """Keys of `table` whose forms occur (longest forms first); all their forms are consumed."""
        entries = sorted(((len(_prep(f)), key, f) for key, forms in table.items() for f in forms), key=lambda x: -x[0])
        hits: list[str] = []
        for _n, key, form in entries:
            if self.find_all([form]) and key not in hits:
                hits.append(key)
        return hits

    def free(self) -> list[tuple[int, str]]:
        return [(i, t) for i, t in enumerate(self.tokens) if not self.used[i]]


def _number(token: str) -> int | None:
    if _DIGITS.match(token):
        return int(token)
    return L.NUMBER_WORDS.get(token)


def _parse_ids(text: str) -> tuple[int | None, int | None]:
    inc = re.search(r"\binc\s*-?\s*0*(\d{1,7})\b", text)
    if inc:
        return int(inc.group(1)), None
    inc_words = r"(?:incident|incidents|घटना|इंसिडेंट|சம்பவம்|சம்பவ எண்)"
    alert_words = r"(?:alert|alerts|अलर्ट|எச்சரிக்கை)"
    num_words = r"(?:\s*(?:number|no|num|नंबर|संख्या|எண்)\s*)?"
    m = re.search(inc_words + r"\s*(?:#|id)?" + num_words + r"\s*(\d{1,7})\b", text)
    if m:
        return int(m.group(1)), None
    m = re.search(alert_words + r"\s*(?:#|id)?" + num_words + r"\s*(\d{1,7})\b", text)
    if m:
        return None, int(m.group(1))
    return None, None


def parse(raw: str, lang: str | None = None) -> ParsedCommand:
    text = normalise(raw)
    tokens = text.split()
    cmd = ParsedCommand(text=text, tokens=tokens, lang=lang if lang in L.LANGS else detect_language(raw))
    if not tokens:
        return cmd
    sc = _Scanner(tokens)

    # 1. explicit incident / alert numbers
    cmd.incident_id, cmd.alert_id = _parse_ids(text)
    if cmd.incident_id or cmd.alert_id:
        for i, t in enumerate(tokens):
            if _DIGITS.match(t) or t.startswith("inc"):
                sc.used[i] = True

    # 2. time window: "<n> <unit>" first, then fixed phrases
    for i in range(len(tokens) - 1):
        n = _number(tokens[i])
        unit = next((u for u in L.TIME_UNITS if _word_match(tokens[i + 1], u) and (len(u) >= 3 or tokens[i + 1] == u)), None)
        if n and unit and not sc.used[i]:
            cmd.hours = min(max(n * L.TIME_UNITS[unit], 1), 24 * 60)
            sc.used[i] = sc.used[i + 1] = True
            # "24 hours" / "मणி நேரம்": also swallow the trailing "नेरम்" / "time" word
            if i + 2 < len(tokens) and tokens[i + 2] in ("நேரம்", "நேரத்தில்", "நேர", "time"):
                sc.used[i + 2] = True
            break
    if cmd.hours is None:
        for hours, forms in L.TIME_PHRASES.items():
            if sc.find(forms):
                cmd.hours = hours
                break
    sc.find(["last", "past", "previous", "पिछले", "पिछला", "pichle", "கடந்த", "kadantha"])

    # 3. superlatives / recency / map view / reset / help / briefing (before single words like "high")
    for verb in ("biggest", "latest", "reset", "help", "brief"):
        if sc.find_all(L.VERBS[verb]):
            cmd.verbs.add(verb)
    # "remove the filters" is a reset; any other remove / delete / change request is refused.
    if "reset" not in cmd.verbs and sc.find_all(L.FORBIDDEN):
        cmd.forbidden = True
    basemap = sc.find_key(L.BASEMAP)
    cmd.basemap = basemap[0] if basemap else None
    sc.find_all(L.VIEW_WORDS)

    # 4. pages named explicitly ("alerts page", "analytics")
    pages = sc.find_key(L.PAGES)
    cmd.page = pages[0] if pages else None

    # 5. places from the gazetteer, before single filter words, so "Mumbai High" / "मुंबई हाई" is a
    #    place and not "Mumbai" + high priority (longest names first).
    places = sc.find_key(L.PLACES)
    cmd.place = places[0] if places else None

    # 6. filters
    classes = sc.find_key(L.CLASSES)
    if "industrial" in classes:
        cmd.industrial = True
    cmd.classes = [c for c in classes if c != "industrial"]
    cmd.facility_types = sc.find_key(L.FACILITY_TYPES_LEX)
    pers = sc.find_key(L.PERSISTENCE_LEX)
    cmd.persistence = pers[0] if pers else None
    dn = sc.find_key(L.DAYNIGHT)
    cmd.daynight = dn[0] if dn else None
    prio = sc.find_key(L.PRIORITY)
    if prio:
        order = ["critical", "high", "medium", "low"]
        cmd.priority = sorted(prio, key=order.index)[0]
    sc.find_all(["priority", "प्राथमिकता", "प्रायोरिटी", "முன்னுரிமை", "priority wale"])

    # 7. what is being asked about (sources before detections: "thermal source" vs "thermal")
    for target in ("sources", "alerts", "incidents", "facilities", "detections"):
        if sc.find_all(L.TARGETS[target]):
            cmd.targets.append(target)


    # 8. remaining verbs
    for verb in ("count", "zoom", "open", "show"):
        if sc.find_all(L.VERBS[verb]):
            cmd.verbs.add(verb)

    # 9. place cues and leftovers (possible place or facility name)
    cue_words = {w for f in L.PLACE_CUES for w in _prep(f)}
    for i, t in sc.free():
        if t in cue_words:
            cmd.place_cue = True
            sc.used[i] = True
    keep = [(i, t) for i, t in sc.free() if t not in L.STOPWORDS and not _DIGITS.match(t) and len(t) > 1]
    cmd.leftover = [t for _i, t in keep]
    if keep:
        # The full span from the first to the last unknown word, including known words inside it:
        # "show jindal steel works" -> "jindal steel works" (a facility name that contains "steel").
        cmd.leftover_span = " ".join(tokens[keep[0][0] : keep[-1][0] + 1])
    return cmd


_TA_SUFFIXES = ["யிலுள்ள", "விலுள்ள", "இலுள்ள", "ிலுள்ள", "யில்", "வில்", "இல்", "ில்", "க்கு", "ுக்கு", "யை", "வை", "ை", "ின்"]


def strip_tamil_case(word: str) -> str:
    """Remove common Tamil case endings from a place word (சென்னையில் -> சென்னை, குஜராத்தில் -> குஜராத்)."""
    for suf in _TA_SUFFIXES:
        if word.endswith(suf) and len(word) > len(suf) + 1:
            stem = word[: -len(suf)]
            # doubled consonant before the ending: குஜராத்த்-இல் -> குஜராத்
            if len(stem) >= 3 and stem[-1] == stem[-3] and stem[-2] == "்":
                stem = stem[:-1]
            return stem
    return word
