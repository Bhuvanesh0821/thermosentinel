"""Free-form voice parser: English, Hindi, Tamil and romanised mixes map onto the same entities.
(Data-backed answers are covered in test_db_integration.)"""

import pytest

from app.voice.interpreter import _filters, _query, local_place_name
from app.voice.parser import detect_language, normalise, parse, strip_tamil_case


def P(text, lang=None):
    return parse(text, lang)


def test_normalise_and_language_detection():
    assert normalise("  Hey, SHOW alerts?! ") == "hey show alerts"
    assert normalise("ज़ूम") == "जूम"  # nukta unified
    assert detect_language("சென்னையில் தீ") == "ta"
    assert detect_language("चेन्नई में आग") == "hi"
    assert detect_language("show fires") == "en"


@pytest.mark.parametrize(
    "text",
    ["Show fires in Chennai today", "आज चेन्नई में आग दिखाओ", "இன்று சென்னையில் தீயைக் காட்டு", "aaj chennai mein aag dikhao"],
)
def test_same_request_in_every_language(text):
    c = P(text)
    assert c.place == "Chennai" and "detections" in c.targets and c.hours == 24 and "show" in c.verbs


@pytest.mark.parametrize(
    "text",
    ["How many high priority incidents are there?", "कितनी उच्च प्राथमिकता वाली घटनाएं हैं?", "எத்தனை உயர் முன்னுரிமை சம்பவங்கள் உள்ளன?"],
)
def test_counting_with_priority(text):
    c = P(text)
    assert "count" in c.verbs and c.targets == ["incidents"] and c.priority == "high"


@pytest.mark.parametrize(
    "text",
    ["Show gas flares at night in the last week", "पिछले हफ्ते रात में गैस फ्लेयर दिखाओ", "கடந்த வாரம் இரவில் வாயு எரிப்பைக் காட்டு"],
)
def test_class_daynight_and_time(text):
    c = P(text)
    assert c.classes == ["gas_flare_like"] and c.daynight == "N" and c.hours == 168


@pytest.mark.parametrize("text", ["Which is the biggest fire in Odisha?", "ओडिशा में सबसे बड़ी आग कौन सी है?", "ஒடிசாவில் மிகப்பெரிய தீ எது?"])
def test_superlative_in_a_state(text):
    c = P(text)
    assert "biggest" in c.verbs and c.place == "Odisha" and not c.leftover


@pytest.mark.parametrize(
    "text,place",
    [("Show steel plants in Jharkhand", "Jharkhand"), ("झारखंड में स्टील प्लांट दिखाओ", "Jharkhand"),
     ("ஜார்கண்டில் எஃகு ஆலைகளைக் காட்டு", "Jharkhand"), ("gujarat mein refinery dikhao", "Gujarat"),
     ("குஜராத்தில் சுத்திகரிப்பு ஆலைகள்", "Gujarat"), ("தமிழ்நாட்டில் சிமெண்ட் ஆலைகள்", "Tamil Nadu")],
)
def test_facility_types_in_places_including_tamil_endings(text, place):
    c = P(text)
    assert c.place == place and c.facility_types and not c.leftover


@pytest.mark.parametrize(
    "text,verb,target",
    [("Open the latest alert", "latest", "alerts"), ("नवीनतम अलर्ट खोलो", "latest", "alerts"),
     ("சமீபத்திய எச்சரிக்கையைத் திற", "latest", "alerts")],
)
def test_latest_alert(text, verb, target):
    c = P(text)
    assert verb in c.verbs and target in c.targets


@pytest.mark.parametrize("text", ["Switch to satellite view", "सैटेलाइट दृश्य दिखाओ", "செயற்கைக்கோள் காட்சியைக் காட்டு"])
def test_basemap(text):
    c = P(text)
    assert c.basemap == "satellite" and not c.leftover


@pytest.mark.parametrize("text", ["Give me a briefing", "स्थिति का सारांश बताओ", "நிலைமை சுருக்கம் சொல்", "what's happening"])
def test_briefing(text):
    c = P(text)
    assert "brief" in c.verbs and not c.leftover


def test_ids_pages_and_reset():
    assert P("open incident 6").incident_id == 6
    assert P("INC-000006").incident_id == 6
    assert P("alert number 234").alert_id == 234
    assert P("open analytics").page == "/analytics"
    assert P("सेटिंग्स खोलो").page == "/settings"
    assert "reset" in P("clear filters").verbs
    assert P("pichle 7 din ki aag").hours == 168


def test_forest_fire_is_not_the_tamil_verb_show():
    c = P("காட்டுத் தீ காட்டு")  # "show forest fires"
    assert c.classes == ["vegetation_fire"] and "show" in c.verbs


def test_facility_name_span_keeps_known_words():
    c = P("show jindal steel works")
    assert c.leftover_span == "jindal steel works"


def test_tamil_case_endings():
    assert strip_tamil_case("சென்னையில்") == "சென்னை"
    assert strip_tamil_case("குஜராத்தில்") == "குஜராத்"
    assert strip_tamil_case("ஒடிசாவில்") == "ஒடிசா"


def test_place_names_are_localised():
    assert local_place_name("Chennai", "ta") == "சென்னை"
    assert local_place_name("Chennai", "hi") == "चेन्नई"
    assert local_place_name("Chennai", "en") == "Chennai"


def test_actions_carry_only_whitelisted_filters():
    c = P("show high priority industrial incidents near refineries in the last 3 days at night")
    f = _filters(c, None)
    assert set(f) <= {"hours", "minPriority", "classification", "facilityType", "persistence", "daynight", "area", "placeBbox", "placeName"}
    assert f["hours"] == 168 and f["minPriority"] == "high" and f["facilityType"] == ["refinery"] and f["daynight"] == "N"
    q = _query("/incidents", c, None)
    assert q.startswith("/incidents?") and "min_priority=high" in q and "facility_type=refinery" in q


@pytest.mark.parametrize(
    "text", ["delete all incidents", "सारे अलर्ट डिलीट करो", "எல்லா சம்பவங்களையும் நீக்கு", "remove the alerts", "email the minister"]
)
def test_destructive_requests_are_flagged(text):
    assert P(text).forbidden


def test_clearing_filters_is_not_destructive():
    for text in ["remove filters", "फ़िल्टर हटाओ", "வடிகட்டிகளை அழி"]:
        c = P(text)
        assert "reset" in c.verbs and not c.forbidden


@pytest.mark.parametrize("text", ["order a pizza", "banana", "", "   "])
def test_nonsense_has_no_actionable_entities(text):
    c = P(text)
    assert not (c.targets or c.has_filters or c.place or c.basemap or c.incident_id or c.alert_id or c.page)


@pytest.mark.parametrize("text", ["show mumbai high", "मुंबई हाई दिखाओ", "மும்பை ஹை காட்டு"])
def test_place_names_win_over_filter_words(text):
    c = P(text)
    assert c.place == "Mumbai High" and c.priority is None
