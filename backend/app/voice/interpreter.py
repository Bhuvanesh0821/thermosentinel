"""Voice / command interpreter - free-form requests in English, Hindi and Tamil.

`interpret(text, conn, lang)` parses the request into entities (see parser.py), decides what the
user wants, answers from stored data and returns ONE safe, whitelisted UI action:

  apply  - open a page and/or set dashboard filters, focus the map on a place, event or
           facility, change the basemap, or clear filters (never writes, deletes or runs jobs)

The reply (`answer`, `interpreted_as`) is in the requested language. Requests that cannot be
mapped onto the application return `supported: false` with suggestions - nothing is executed.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.analytics.classifier import CLASSES, INCIDENT_CLASSES
from app.ingestion.facilities.classify import FACILITY_TYPES
from app.voice import lexicon as L
from app.voice.parser import ParsedCommand, parse, strip_tamil_case

INDUSTRIAL_CLASSES = ["gas_flare_like", "industrial_associated_event", "mining_associated", "persistent_industrial_source"]
EXAMPLES = L.EXAMPLES["en"]  # kept for /api/voice/commands
DEFAULT_HOURS = 48
PRIORITY_ORDER = ["low", "medium", "high", "critical"]


@dataclass
class Interpretation:
    supported: bool
    intent: str | None
    interpreted_as: str
    action: dict | None = None
    answer: str | None = None
    data: dict | None = None
    suggestions: list[str] = field(default_factory=list)
    lang: str = "en"
    understood: list[str] = field(default_factory=list)  # the entities recognised, in the user's language

    def as_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- helpers
def _t(key: str, lang: str, **kw) -> str:
    return L.T[key][lang].format(**kw)


def _label(kind: str, lang: str) -> str:
    return L.LABELS[kind][lang]


def _fac_label(ftype: str, lang: str) -> str:
    return FACILITY_TYPES.get(ftype, ftype) if lang == "en" else L.FACILITY_TEXT[lang].get(ftype, ftype)


def _class_label(cls: str, lang: str) -> str:
    return CLASSES.get(cls, cls) if lang == "en" else L.CLASS_TEXT[lang].get(cls, cls)


def _severity(sev: str, lang: str) -> str:
    return L.PRIORITY_TEXT[lang].get(sev, sev)


def _classes(cmd: ParsedCommand) -> list[str]:
    cls = list(cmd.classes)
    if cmd.industrial:
        cls += [c for c in INDUSTRIAL_CLASSES if c not in cls]
    if cmd.persistence == "persistent" and cmd.industrial:
        cls = [c for c in cls if c != "industrial_associated_event"] or cls
    return cls


def local_place_name(name: str, lang: str) -> str:
    """The gazetteer spelling in the user's script (சென்னை / चेन्नई), else the English name."""
    if lang == "en":
        return name
    lo, hi = ("஀", "௿") if lang == "ta" else ("ऀ", "ॿ")
    return next((f for f in L.PLACES.get(name, []) if any(lo <= c <= hi for c in f) and " " not in f or
                 (any(lo <= c <= hi for c in f) and f.count(" ") < 2)), name)


def _chips(cmd: ParsedCommand, lang: str, place: dict | None = None, near: bool = True) -> list[str]:
    """What was understood, as short labels in the user's language."""
    out = []
    if place:
        out.append(place["name"])
    if cmd.priority:
        out.append(L.PRIORITY_MIN_TEXT[lang].format(p=_severity(cmd.priority, lang)))
    if cmd.industrial:
        out.append(L.INDUSTRIAL_TEXT[lang])
    out += [_class_label(c, lang) for c in cmd.classes]
    out += [L.NEAR_TEXT[lang].format(x=_fac_label(f, lang)) if near else _fac_label(f, lang) for f in cmd.facility_types]
    if cmd.persistence:
        out.append(L.PERSIST_TEXT[lang][cmd.persistence])
    if cmd.daynight:
        out.append(L.NIGHT_TEXT[lang][cmd.daynight])
    if cmd.hours:
        out.append(L.window_label(cmd.hours, lang))
    return out


def _desc(chips: list[str]) -> str:
    return f" ({', '.join(chips)})" if chips else ""


def _dashboard_hours(hours: int | None) -> int:
    """Nearest dashboard window at or above the request (24 h, 48 h, 7 d, 30 d)."""
    if not hours:
        return DEFAULT_HOURS
    return next((w for w in (24, 48, 168, 720) if hours <= w), 720)


def _zoom_for(bbox: list[float] | None, default: float = 9) -> float:
    if not bbox:
        return default
    w = max(bbox[2] - bbox[0], (bbox[3] - bbox[1]) * 1.3, 0.05)
    return round(max(4.5, min(12.0, math.log2(360 / w) - 0.4)), 1)


def _filters(cmd: ParsedCommand, place: dict | None) -> dict:
    f: dict = {"hours": _dashboard_hours(cmd.hours)}
    if cmd.priority:
        f["minPriority"] = cmd.priority
    cls = _classes(cmd)
    if cls:
        f["classification"] = cls
    if cmd.facility_types:
        f["facilityType"] = cmd.facility_types
    if cmd.persistence:
        f["persistence"] = [cmd.persistence]
    if cmd.daynight:
        f["daynight"] = cmd.daynight
    if place and place.get("bbox"):
        f.update(area="place", placeBbox=place["bbox"], placeName=place["name"])
    return f


def _query(path: str, cmd: ParsedCommand, place: dict | None, extra: dict | None = None) -> str:
    params = {}
    if cmd.hours:
        params["hours"] = _dashboard_hours(cmd.hours)
    if cmd.priority:
        params["min_priority"] = cmd.priority
    cls = _classes(cmd)
    if cls:
        params["classification"] = ",".join(cls)
    if cmd.facility_types:
        params["facility_type"] = ",".join(cmd.facility_types)
    if cmd.persistence:
        params["persistence"] = cmd.persistence
    if cmd.daynight:
        params["daynight"] = cmd.daynight
    if place and place.get("bbox"):
        params["bbox"] = ",".join(f"{v:.4f}" for v in place["bbox"])
        params["place"] = place["name"]
    params.update(extra or {})
    return path + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")


def _bbox_sql(alias_lat: str, alias_lon: str, place: dict | None, params: dict) -> str:
    if not place or not place.get("bbox"):
        return ""
    w, s, e, n = place["count_bbox"]
    params.update(bw=w, bs=s, be=e, bn=n)
    return f" AND {alias_lon} BETWEEN :bw AND :be AND {alias_lat} BETWEEN :bs AND :bn"


# --------------------------------------------------------------------------- place / facility resolution
def resolve_place(cmd: ParsedCommand) -> tuple[dict | None, str | None]:
    """(place, not_found_name). Gazetteer first, then the geocoder for unknown words after a place cue."""
    from app.search.service import search_locations

    query = cmd.place
    if not query and cmd.leftover:
        words = [strip_tamil_case(w) if cmd.lang == "ta" or any("஀" <= c <= "௿" for c in w) else w for w in cmd.leftover]
        query = " ".join(words)
    if not query:
        return None, None
    hits = search_locations(query, 1)
    if not hits:
        return None, query
    h = hits[0]
    name = local_place_name(cmd.place, cmd.lang) if cmd.place else h["label"]
    bbox = h.get("bbox") or [h["lon"] - 0.25, h["lat"] - 0.25, h["lon"] + 0.25, h["lat"] + 0.25]
    kind = (h.get("place_type") or "").lower()
    # A city's administrative box is small; count within ~40 km so "fires in Chennai" includes its surroundings.
    pad = 0.0 if kind in ("state", "region", "province") or (bbox[2] - bbox[0]) > 1.5 else 0.35
    count_bbox = [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad]
    return {"name": name, "lat": h["lat"], "lon": h["lon"], "bbox": count_bbox, "count_bbox": count_bbox,
            "zoom": _zoom_for(count_bbox), "kind": kind}, None


def find_facility(conn: Connection, cmd: ParsedCommand) -> dict | None:
    from app.search.service import search_facilities

    for q in filter(None, [cmd.leftover_span, " ".join(cmd.leftover) if cmd.leftover else None]):
        if len(q) >= 3:
            hits = search_facilities(conn, q, 1)
            if hits:
                return hits[0]
    return None


# --------------------------------------------------------------------------- data queries (real, stored data)
def _cluster_filter_sql(cmd: ParsedCommand, params: dict, alias: str = "c") -> str:
    sql = ""
    cls = _classes(cmd)
    if cls:
        sql += f" AND {alias}.classification = ANY(CAST(:classes AS text[]))"
        params["classes"] = cls
    if cmd.facility_types:
        sql += (f" AND {alias}.industrial_association AND EXISTS (SELECT 1 FROM industrial_facilities f"
                f" WHERE f.id = {alias}.nearest_facility_id AND f.facility_type = ANY(CAST(:ftypes AS text[])))")
        params["ftypes"] = cmd.facility_types
    if cmd.persistence:
        sql += f" AND {alias}.persistence_category = :pers"
        params["pers"] = cmd.persistence
    if cmd.priority:
        sql += f" AND {alias}.priority = ANY(CAST(:prios AS text[]))"
        params["prios"] = PRIORITY_ORDER[PRIORITY_ORDER.index(cmd.priority):]
    return sql


def count_detections(conn: Connection, cmd: ParsedCommand, place: dict | None, hours: int) -> tuple[int, int]:
    params: dict = {"h": hours}
    where = "o.acquired_at >= now() - make_interval(hours => :h)" + _bbox_sql("o.latitude", "o.longitude", place, params)
    if cmd.daynight:
        where += " AND o.daynight = :dn"
        params["dn"] = cmd.daynight
    cf = _cluster_filter_sql(cmd, params)
    join = " JOIN thermal_clusters c ON c.id = o.cluster_id" if cf else ""
    row = conn.execute(
        text(f"SELECT count(*), count(*) FILTER (WHERE o.daynight = 'N') FROM thermal_observations o{join} WHERE {where}{cf}"),
        params,
    ).one()
    return int(row[0]), int(row[1])


def count_incidents(conn: Connection, cmd: ParsedCommand, place: dict | None) -> int:
    params: dict = {}
    sql = "SELECT count(*) FROM incidents i JOIN thermal_clusters c ON c.id = i.cluster_id WHERE i.status IN ('active','monitoring')"
    sql += _bbox_sql("i.latitude", "i.longitude", place, params)
    if cmd.hours:
        sql += " AND i.last_detected_at >= now() - make_interval(hours => :h)"
        params["h"] = cmd.hours
    return int(conn.execute(text(sql + _cluster_filter_sql(cmd, params)), params).scalar_one())


def count_alerts(conn: Connection, cmd: ParsedCommand, place: dict | None) -> int:
    params: dict = {}
    sql = "SELECT count(*) FROM alerts a WHERE a.status = 'open'" + _bbox_sql("a.latitude", "a.longitude", place, params)
    if cmd.priority:
        sql += " AND a.severity = ANY(CAST(:sev AS text[]))"
        params["sev"] = PRIORITY_ORDER[PRIORITY_ORDER.index(cmd.priority):]
    if cmd.hours:
        sql += " AND a.last_triggered_at >= now() - make_interval(hours => :h)"
        params["h"] = cmd.hours
    return int(conn.execute(text(sql), params).scalar_one())


def count_sources(conn: Connection, cmd: ParsedCommand, place: dict | None) -> tuple[int, int]:
    params: dict = {}
    sql = ("SELECT count(*), count(*) FILTER (WHERE c.industrial_association) FROM thermal_clusters c "
           "WHERE c.status = 'active' AND c.persistence_category = :p")
    params["p"] = cmd.persistence or "persistent"
    sql += _bbox_sql("c.center_latitude", "c.center_longitude", place, params)
    sub = ParsedCommand(**{**cmd.__dict__, "persistence": None})
    row = conn.execute(text(sql + _cluster_filter_sql(sub, params)), params).one()
    return int(row[0]), int(row[1])


def count_facilities(conn: Connection, cmd: ParsedCommand, place: dict | None) -> int:
    params: dict = {}
    sql = "SELECT count(*) FROM industrial_facilities f WHERE f.is_active" + _bbox_sql("f.latitude", "f.longitude", place, params)
    if cmd.facility_types:
        sql += " AND f.facility_type = ANY(CAST(:ftypes AS text[]))"
        params["ftypes"] = cmd.facility_types
    return int(conn.execute(text(sql), params).scalar_one())


_EVENT_COLUMNS = """c.id, c.center_latitude AS lat, c.center_longitude AS lon, c.classification, c.max_frp, c.end_time,
                    i.id AS incident_id, f.name AS facility_name"""
_EVENT_JOINS = """LEFT JOIN incidents i ON i.cluster_id = c.id
                  LEFT JOIN industrial_facilities f ON f.id = c.nearest_facility_id AND c.industrial_association"""


def top_event(conn: Connection, cmd: ParsedCommand, place: dict | None, order: str) -> dict | None:
    params: dict = {"h": cmd.hours or 168}
    sql = (f"SELECT {_EVENT_COLUMNS} FROM thermal_clusters c {_EVENT_JOINS} "
           "WHERE c.status = 'active' AND c.end_time >= now() - make_interval(hours => :h)")
    sql += _bbox_sql("c.center_latitude", "c.center_longitude", place, params) + _cluster_filter_sql(cmd, params)
    if cmd.daynight == "N":
        sql += " AND c.night_fraction > 0"
    row = conn.execute(text(sql + f" ORDER BY {order} LIMIT 1"), params).mappings().one_or_none()
    return dict(row) if row else None


# --------------------------------------------------------------------------- decision
def _unsupported(cmd: ParsedCommand, raw: str) -> Interpretation:
    lang = cmd.lang
    return Interpretation(
        False, None, f"{_label('unsupported', lang)}: “{raw.strip()}”", answer=_t("unsupported", lang),
        suggestions=L.EXAMPLES[lang], lang=lang,
    )


def _apply(path: str, **kw) -> dict:
    return {"type": "apply", "path": path, **{k: v for k, v in kw.items() if v is not None}}


def _event_answer(ev: dict, lang: str) -> tuple[str, str]:
    label = _class_label(ev["classification"], lang)
    at = ""
    if ev.get("facility_name"):
        at = f" at {ev['facility_name']}" if lang == "en" else f" - {ev['facility_name']}"
    return label, at


def interpret(raw: str, conn: Connection, lang: str | None = None) -> Interpretation:
    cmd = parse(raw, lang)
    lg = cmd.lang
    if not cmd.tokens:
        return _unsupported(cmd, raw)
    if cmd.forbidden:
        return Interpretation(False, "forbidden", f"{_label('forbidden', lg)}: “{raw.strip()}”",
                              answer=_t("forbidden", lg), suggestions=L.EXAMPLES[lg], lang=lg)
    anything = bool(cmd.targets or cmd.has_filters or cmd.place or cmd.leftover or cmd.page or cmd.basemap
                    or cmd.incident_id or cmd.alert_id or cmd.verbs - {"help"})

    # --- help
    if "help" in cmd.verbs and not anything:
        return Interpretation(True, "help", _label("help", lg), answer=_t("help", lg), suggestions=L.EXAMPLES[lg], lang=lg)

    # --- clear filters
    if "reset" in cmd.verbs:
        return Interpretation(True, "reset", _label("reset", lg), action=_apply("/dashboard", reset=True),
                              answer=_t("reset", lg), lang=lg)

    # --- basemap
    if cmd.basemap:
        return Interpretation(True, "basemap", f"{_label('basemap', lg)}: {cmd.basemap}",
                              action=_apply("/dashboard", basemap=cmd.basemap),
                              answer=_t(f"basemap_{cmd.basemap}", lg), lang=lg)

    # --- a specific incident / alert
    if cmd.incident_id:
        row = conn.execute(text("SELECT id, title FROM incidents WHERE id = :i"), {"i": cmd.incident_id}).mappings().one_or_none()
        if not row:
            return Interpretation(True, "open_incident", f"{_label('open', lg)} INC-{cmd.incident_id:06d}",
                                  answer=_t("no_incident", lg, id=cmd.incident_id), lang=lg)
        ref = f"INC-{row['id']:06d}"
        return Interpretation(True, "open_incident", f"{_label('open', lg)} {ref}", action=_apply(f"/investigation/{row['id']}"),
                              answer=_t("open_incident", lg, ref=ref, title=row["title"]), data=dict(row), lang=lg)
    if cmd.alert_id:
        row = conn.execute(text("SELECT id, incident_id, title, severity FROM alerts WHERE id = :a"), {"a": cmd.alert_id}).mappings().one_or_none()
        if not row:
            return Interpretation(True, "open_alert", f"{_label('open', lg)} #{cmd.alert_id}", answer=_t("no_alert", lg, id=cmd.alert_id), lang=lg)
        path = f"/investigation/{row['incident_id']}" if row["incident_id"] else "/alerts"
        return Interpretation(True, "open_alert", f"{_label('open', lg)} #{row['id']}", action=_apply(path),
                              answer=_t("open_alert", lg, severity=_severity(row["severity"], lg), id=row["id"], title=row["title"]),
                              data=dict(row), lang=lg)

    # --- latest alert
    if "latest" in cmd.verbs and "alerts" in cmd.targets:
        row = conn.execute(text("SELECT id, incident_id, title, severity FROM alerts ORDER BY last_triggered_at DESC LIMIT 1")).mappings().one_or_none()
        if not row:
            return Interpretation(True, "open_latest_alert", _label("latest", lg), answer=_t("no_alerts", lg), lang=lg)
        path = f"/investigation/{row['incident_id']}" if row["incident_id"] else "/alerts"
        return Interpretation(True, "open_latest_alert", f"{_label('latest', lg)}: {row['title']}",
                              action=_apply(path, alert_id=row["id"]),
                              answer=_t("latest_alert", lg, severity=_severity(row["severity"], lg), title=row["title"]),
                              data=dict(row), lang=lg)

    # --- briefing (unless it is about a particular place: "what is happening near Jamnagar")
    if "brief" in cmd.verbs and not (cmd.place or cmd.leftover):
        return _briefing(conn, cmd)

    # --- place / facility named in the request
    place, not_found = (None, None)
    facility = None
    if cmd.place:
        place, not_found = resolve_place(cmd)
    elif cmd.leftover:
        facility = find_facility(conn, cmd)
        # Unknown words are only treated as a place when the request says so ("in X", "zoom to X",
        # "show X"); anything else ("order a pizza") is reported as not understood.
        if not facility and (cmd.place_cue or cmd.verbs & {"zoom", "show", "count", "biggest", "latest"}):
            place, not_found = resolve_place(cmd)
    if not_found and not (cmd.targets or cmd.has_filters):
        return Interpretation(True, "zoom_to_place", f"{_label('zoom', lg)}: {not_found}", answer=_t("place_not_found", lg, place=not_found), lang=lg)
    if cmd.leftover and not (place or facility or cmd.targets or cmd.has_filters or cmd.page or cmd.verbs - {"show", "open"}):
        return _unsupported(cmd, raw)

    chips = _chips(cmd, lg, place)
    hours = cmd.hours or DEFAULT_HOURS
    focus = {"lon": place["lon"], "lat": place["lat"], "zoom": place["zoom"], "bbox": place["bbox"]} if place else None

    # --- latest / most intense thermal event
    if cmd.verbs & {"latest", "biggest"}:
        biggest = "biggest" in cmd.verbs
        ev = top_event(conn, cmd, place, "c.max_frp DESC NULLS LAST" if biggest else "c.end_time DESC")
        intent = "hottest_event" if biggest else "latest_event"
        head = _label("hottest" if biggest else "latest", lg)
        if not ev:
            scope = f" ({', '.join(chips)})" if chips else ""
            return Interpretation(True, intent, f"{head}{_desc(chips)}", answer=_t("no_event", lg, scope=scope), lang=lg, understood=chips)
        label, at = _event_answer(ev, lg)
        action = _apply("/dashboard", filters=_filters(cmd, place),
                        focus={"lon": ev["lon"], "lat": ev["lat"], "zoom": 12},
                        selection={"type": "cluster", "id": ev["id"], "incidentId": ev["incident_id"]})
        if biggest:
            where = L.area_text(place["name"], lg) if place else ""
            answer = _t("hottest", lg, when=L.when_text(cmd.hours or 168, lg), where=where, label=label, at=at,
                        frp=f"{ev['max_frp'] or 0:.1f}")
        else:
            answer = _t("latest_event", lg, label=label, at=at)
        return Interpretation(True, intent, f"{head}{_desc(chips)}", action=action, answer=answer,
                              data={k: ev[k] for k in ("id", "lat", "lon", "max_frp", "end_time", "incident_id")}, lang=lg, understood=chips)

    # --- counting questions
    if "count" in cmd.verbs:
        target = next((t for t in ("alerts", "incidents", "sources", "facilities") if t in cmd.targets), None)
        if target is None and cmd.persistence == "persistent" and "detections" not in cmd.targets:
            target = "sources"
        head = f"{_label('count', lg)}: {L.THING_TEXT[lg][target or 'detections']}{_desc(chips)}"
        if target == "alerts":
            n = count_alerts(conn, cmd, place)
            return Interpretation(True, "count_alerts", head, answer=_t("count_alerts", lg, desc=_desc(chips), n=n),
                                  data={"open": n}, lang=lg, understood=chips)
        if target == "incidents":
            n = count_incidents(conn, cmd, place)
            return Interpretation(True, "count_incidents", head, answer=_t("count_incidents", lg, desc=_desc(chips), n=n),
                                  data={"open": n}, lang=lg, understood=chips)
        if target == "sources":
            n, ind = count_sources(conn, cmd, place)
            return Interpretation(True, "count_persistent_sources", head,
                                  action=_apply(_query("/thermal-sources", cmd, place, {"persistence": cmd.persistence or "persistent"})),
                                  answer=_t("count_sources", lg, desc=_desc(chips), n=n, ind=ind),
                                  data={"total": n, "industrial": ind}, lang=lg, understood=chips)
        if target == "facilities":
            n = count_facilities(conn, cmd, place)
            return Interpretation(True, "count_facilities", head, answer=_t("count_facilities", lg, desc=_desc(chips), n=n),
                                  data={"facilities": n}, lang=lg, understood=chips)
        n, night = count_detections(conn, cmd, place, hours)
        where = L.area_text(place["name"], lg) if place else ""
        return Interpretation(True, "count_detections", head,
                              answer=_t("count_detections", lg, n=n, night=night, where=where, when=L.when_text(hours, lg)),
                              data={"detections": n, "night": night, "hours": hours}, lang=lg, understood=chips)

    # --- a named facility ("show Jindal Steel Works")
    if facility and not place:
        label = facility["label"]
        ftype = next((k for k, v in FACILITY_TYPES.items() if facility["detail"].startswith(v)), None)
        return Interpretation(True, "zoom_to_facility", f"{_label('zoom', lg)}: {label}",
                              action=_apply("/dashboard", focus={"lon": facility["lon"], "lat": facility["lat"], "zoom": 13},
                                            selection={"type": "facility", "id": facility["id"], "lon": facility["lon"], "lat": facility["lat"]},
                                            layers={"facilities": True, "footprints": True}),
                              answer=_t("facility_zoom", lg, name=label, type=_fac_label(ftype, lg) if ftype else facility["detail"]),
                              data=facility, lang=lg, understood=[label])

    # --- a page asked for by name
    if cmd.page and not (place or cmd.has_filters):
        return Interpretation(True, "navigate", f"{_label('open', lg)}: {L.PAGE_TEXT[lg][cmd.page]}", action=_apply(cmd.page),
                              answer=_t("open_page", lg, page=L.PAGE_TEXT[lg][cmd.page]), lang=lg)

    # --- lists of incidents / alerts / sources / facilities (optionally in a place)
    list_target = next((t for t in ("alerts", "incidents", "sources") if t in cmd.targets), None)
    if list_target or (cmd.page in ("/incidents", "/alerts", "/thermal-sources")):
        list_target = list_target or {"/incidents": "incidents", "/alerts": "alerts", "/thermal-sources": "sources"}[cmd.page]
        head = f"{_label('show', lg)}: {L.THING_TEXT[lg][list_target]}{_desc(chips)}"
        if list_target == "alerts":
            n = count_alerts(conn, cmd, place)
            extra = {"severity": cmd.priority} if cmd.priority else {}
            path = "/alerts" + ("?" + "&".join(f"{k}={v}" for k, v in extra.items()) if extra else "")
        elif list_target == "incidents":
            n = count_incidents(conn, cmd, place)
            path = _query("/incidents", cmd, place)
        else:
            n, _ind = count_sources(conn, cmd, place)
            path = _query("/thermal-sources", cmd, place, {} if cmd.persistence else {"persistence": "persistent,recurring"})
        return Interpretation(True, f"show_{list_target}", head, action=_apply(path),
                              answer=_t("show_list", lg, n=n, things=L.THING_TEXT[lg][list_target], desc=_desc(chips)),
                              data={"count": n}, lang=lg, understood=chips)

    # --- facilities of a type / in a place, shown on the map
    if "facilities" in cmd.targets or (cmd.facility_types and not cmd.targets and not _classes(cmd)):
        n = count_facilities(conn, cmd, place)
        chips = _chips(cmd, lg, place, near=False)
        head = f"{_label('show', lg)}: {L.THING_TEXT[lg]['facilities']}{_desc(chips)}"
        return Interpretation(True, "show_facilities", head,
                              action=_apply("/dashboard", filters=_filters(cmd, place), focus=focus,
                                            layers={"facilities": True}),
                              answer=_t("count_facilities", lg, desc=_desc(chips), n=n), data={"facilities": n},
                              lang=lg, understood=chips)

    # --- a place: zoom there with any filters and summarise it
    if place:
        n, _night = count_detections(conn, cmd, place, hours)
        inc = count_incidents(conn, cmd, place)
        return Interpretation(True, "zoom_to_place", f"{_label('zoom', lg)}: {place['name']}{_desc(chips[1:])}",
                              action=_apply("/dashboard", filters=_filters(cmd, place), focus=focus),
                              answer=_t("zoom_place", lg, place=place["name"], n=n, inc=inc, when=L.when_text(hours, lg)),
                              data={"detections": n, "incidents": inc, "place": place}, lang=lg, understood=chips)

    # --- detections / filters on the map
    if cmd.has_filters or "detections" in cmd.targets or (cmd.page == "/dashboard"):
        n, _night = count_detections(conn, cmd, None, hours)
        desc = ", ".join(chips) if chips else L.THING_TEXT[lg]["detections"]
        return Interpretation(True, "show_on_map", f"{_label('show', lg)}: {desc}",
                              action=_apply("/dashboard", filters=_filters(cmd, None), layers={"hotspots": True}),
                              answer=_t("show_map", lg, desc=desc, n=n, when=L.when_text(hours, lg)),
                              data={"detections": n, "hours": hours}, lang=lg, understood=chips)

    if cmd.page:
        return Interpretation(True, "navigate", f"{_label('open', lg)}: {L.PAGE_TEXT[lg][cmd.page]}", action=_apply(cmd.page),
                              answer=_t("open_page", lg, page=L.PAGE_TEXT[lg][cmd.page]), lang=lg)
    if not_found:
        return Interpretation(True, "zoom_to_place", f"{_label('zoom', lg)}: {not_found}", answer=_t("place_not_found", lg, place=not_found), lang=lg)
    return _unsupported(cmd, raw)


def _briefing(conn: Connection, cmd: ParsedCommand) -> Interpretation:
    from app.voice.briefing import build_briefing

    lg = cmd.lang
    hours = cmd.hours or 24
    b = build_briefing(conn, hours)
    if lg == "en":
        answer = b["text"]
    else:
        f = b["facts"]
        inc = f["incidents"]
        answer = L.T["briefing"][lg].format(
            when=L.when_text(hours, lg), det=f["detections"], clusters=f["clusters"]["active"],
            ind=f["clusters"]["industrial_associated"], pers=f["clusters"]["persistent"],
            open=inc["active"] + inc["monitoring"], c=inc["critical"], h=inc["high"], m=inc["medium"], alerts=f["open_alerts"],
        )
    return Interpretation(True, "briefing", _label("brief", lg), answer=answer, data=b["facts"], lang=lg)
