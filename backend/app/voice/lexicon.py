"""Multilingual vocabulary for voice / typed commands: English, Hindi and Tamil.

Each concept lists surface forms in English, Hindi (Devanagari), Tamil (Tamil script) and the
romanised Hinglish / Tanglish people actually speak. Forms are matched as word *stems* (a token
matches when it starts with the stem), which covers plurals and Tamil case endings
(சென்னையில் -> சென்னை, அலர்ட்களை -> அலர்ட்). Stems shorter than three characters only match
whole words. Multi-word forms match consecutive tokens.

Nothing here is data: it is only the language needed to map a request onto the real API.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- actions / verbs
VERBS: dict[str, list[str]] = {
    "show": [
        "show", "display", "list", "view", "see", "find", "get", "bring up", "look at", "where are", "which are",
        "दिखा", "दिखाओ", "दिखाइए", "दिखाएं", "दिखाये", "दिखाना", "बताओ", "बताइए", "बताएं", "बता", "ढूंढो", "खोजो",
        "dikha", "dikhao", "dikhaiye", "dikhana", "batao", "bataiye", "dhundo", "khojo",
        "காட்டு", "காட்டவும்", "காட்டுங்கள்", "காண்பி", "காண்பிக்கவும்", "தேடு", "பார்", "சொல்", "கூறு",
        "kaattu", "kaatu", "kattu", "kaatunga", "kaanbi", "kanbi", "thedu", "paaru", "sollu",
    ],
    "open": [
        "open", "go to", "goto", "navigate", "take me", "switch to", "bring me",
        "खोलो", "खोलिए", "खोलें", "खोल", "जाओ", "ले चलो", "ले जाओ", "kholo", "kholiye", "khol", "jao", "le chalo",
        "திற", "திறக்கவும்", "திறங்கள்", "செல்", "போ", "thira", "thiravu", "thirakkavum", "sel",
    ],
    "zoom": [
        "zoom", "fly", "pan", "centre", "center", "focus", "take me to",
        "ज़ूम", "जूम", "zoom karo", "ஜூம்", "பெரிதாக்கு", "periyathaakku",
    ],
    "count": [
        "how many", "how much", "count", "number of", "total", "no of",
        "कितने", "कितनी", "कितना", "संख्या", "गिनती", "kitne", "kitni", "kitna", "sankhya", "ginti",
        "எத்தனை", "எவ்வளவு", "மொத்தம்", "எண்ணிக்கை", "ethanai", "ettanai", "evvalavu", "mottham",
    ],
    "help": [
        "help", "what can you do", "what can i say", "commands", "how to use",
        "मदद", "सहायता", "madad", "sahayata", "உதவி", "udhavi", "uthavi",
    ],
    "brief": [
        "briefing", "brief me", "summary", "summarise", "summarize", "situation", "status report", "sitrep",
        "overview", "what is happening", "what's happening", "whats happening", "update me",
        "सारांश", "स्थिति", "ब्रीफिंग", "क्या हो रहा", "हालात", "saransh", "sthiti", "kya ho raha", "halat",
        "சுருக்கம்", "நிலைமை", "நிலவரம்", "என்ன நடக்கிறது", "என்ன நடக்குது", "surukkam", "nilaimai", "nilavaram",
        "enna nadakkuthu", "enna nadakkirathu",
    ],
    "reset": [
        "reset", "clear filter", "clear the filter", "remove filter", "clear all", "show everything", "all india",
        "फ़िल्टर हटा", "फिल्टर हटा", "फिल्टर साफ", "रीसेट", "सब दिखा", "पूरा भारत", "filter hatao", "reset karo", "sab dikhao",
        "வடிகட்டி", "ரீசெட்", "முழு இந்தியா", "filter azhi", "ellam kaattu",
    ],
    "latest": [
        "latest", "newest", "most recent", "recent", "new",
        "नवीनतम", "ताज़ा", "ताजा", "सबसे नया", "सबसे नई", "नया", "नई", "लेटेस्ट", "हाल का", "हाल की",
        "naya", "nayi", "taza", "sabse naya", "sabse nayi",
        "சமீபத்திய", "புதிய", "லேட்டஸ்ட்", "கடைசி", "sameebathiya", "puthiya", "pudhiya", "kadaisi",
    ],
    "biggest": [
        "biggest", "largest", "hottest", "most intense", "strongest", "highest", "worst", "most severe", "top", "maximum",
        "सबसे बड़ा", "सबसे बड़ी", "सबसे बड़े", "सबसे तेज", "सबसे गर्म", "सबसे ज्यादा", "सबसे अधिक", "सबसे भीषण",
        "sabse bada", "sabse badi", "sabse bade", "sabse tez", "sabse garam", "sabse jyada", "sabse zyada",
        "மிகப்பெரிய", "மிகப் பெரிய", "மிகப்பெரும்", "மிக அதிக", "அதிகபட்ச", "மிகத் தீவிர", "மிக தீவிர", "பெரிய",
        "mikapperiya", "periya", "athigapatcha",
    ],
}

# Requests to change or destroy data are refused explicitly (the voice interface is read-only).
FORBIDDEN = [
    "delete", "remove", "erase", "drop", "destroy", "wipe", "purge", "truncate", "kill", "shutdown", "shut down",
    "disable", "hack", "modify", "edit", "update the", "change the data", "send email", "send an email", "email",
    "डिलीट", "मिटा", "मिटाओ", "नष्ट", "बंद करो", "हटाओ", "हटा दो", "delete karo", "mita do", "hata do",
    "நீக்கு", "அழி", "அழிக்கவும்", "நீக்கவும்", "டிலீட்", "மாற்று", "delete pannu", "azhi",
]

# --------------------------------------------------------------------------- what the user asks about
TARGETS: dict[str, list[str]] = {
    "incidents": [
        "incident", "event", "case",
        "घटना", "घटनाएं", "घटनाओं", "इंसिडेंट", "इन्सिडेंट", "ghatna", "ghatnaye", "incident",
        "சம்பவ", "நிகழ்வு", "இன்சிடென்ட்", "sambavam", "sambavangal", "nigazhvu",
    ],
    "alerts": [
        "alert", "warning", "alarm",
        "अलर्ट", "चेतावनी", "चेतावनियां", "alert", "chetavani",
        "எச்சரிக்கை", "அலர்ட்", "echarikkai", "alertu",
    ],
    "sources": [
        "thermal source", "heat source", "persistent source", "source",
        "ताप स्रोत", "स्रोत", "srot", "வெப்ப மூல", "மூலங்", "moolam",
    ],
    "facilities": [
        "facility", "facilities", "factory", "factories", "industries", "plant", "sites", "infrastructure",
        "प्लांट", "संयंत्र", "பிளான்ட்", "பிளாண்ட்", "ஆலை",
        "सुविधा", "सुविधाएं", "कारखान", "फैक्ट्री", "फ़ैक्टरी", "उद्योगों", "karkhana", "karkhane", "factory",
        "தொழிற்சாலை", "ஆலைகள்", "பேக்டரி", "தொழிற்சாலைக", "thozhirsalai", "aalai",
    ],
    "detections": [
        "detection", "fire", "hotspot", "hot spot", "heat", "anomal", "thermal", "burning", "flames", "blaze",
        "आग", "आगें", "फायर", "हॉटस्पॉट", "हॉट स्पॉट", "डिटेक्शन", "गर्मी", "ताप", "जलना", "जल रहा",
        "aag", "fire", "garmi", "taap", "jal raha",
        "தீ", "தீயை", "தீயைக்", "தீயைக", "தீக்கள்", "தீக்களை", "தீயின்", "தீயில்", "நெருப்பு", "வெப்பம்", "வெப்பக்",
        "ஹாட்ஸ்பாட்", "ஃபயர்", "எரிவது", "எரியும்", "thee", "theeyai", "neruppu", "veppam",
    ],
}

# --------------------------------------------------------------------------- filters
PRIORITY: dict[str, list[str]] = {
    "critical": ["critical", "severe", "urgent", "emergency", "गंभीर", "क्रिटिकल", "अति गंभीर", "gambhir", "critical",
                 "மிக அவசர", "அவசர", "கிரிட்டிக்கல்", "தீவிர", "avasara", "theevira"],
    "high": ["high", "हाई", "उच्च", "ऊंची", "ऊँची", "uchch", "uchcha", "high", "ஹை", "உயர்", "uyar"],
    "medium": ["medium", "moderate", "मध्यम", "मीडियम", "madhyam", "நடுத்தர", "மிதமான", "நடுநிலை", "naduthara"],
    "low": ["low", "minor", "कम", "लो", "निम्न", "kam", "குறைந்த", "குறைவு", "kuraindha", "kuraivu"],
}
# "industrial" means the four facility-linked classes (see INDUSTRIAL_CLASSES in the interpreter).
CLASSES: dict[str, list[str]] = {
    "gas_flare_like": ["gas flare", "flare", "flaring", "गैस फ्लेयर", "फ्लेयर", "गैस फ्लेयरिंग", "gas flare",
                       "வாயு எரிப்", "ஃப்ளேர்", "ப்ளேர்", "எரிவாயு எரிப்", "flare"],
    "industrial": ["industrial", "industry", "औद्योगिक", "इंडस्ट्रियल", "उद्योग", "audyogik", "udyog", "industrial",
                   "தொழில்துறை", "தொழில் துறை", "தொழிற்துறை", "thozhilthurai"],
    "agricultural_burning": ["crop", "stubble", "farm fire", "agricultur", "paddy", "straw", "पराली", "फसल", "खेत",
                             "पुआल", "parali", "fasal", "khet", "பயிர்", "வைக்கோல்", "வயல்", "விவசாய", "payir", "vaikkol", "vayal"],
    "vegetation_fire": ["forest", "wildfire", "wild fire", "vegetation", "jungle", "bush fire", "जंगल", "वन", "वनाग्नि",
                        "jungle", "jangal", "காடு", "காட்டுத்", "காட்டு தீ", "வனத்", "kaadu", "kattu thee"],
    "unclassified_anomaly": ["unclassified", "unknown", "अवर्गीकृत", "अज्ञात", "வகைப்படுத்தப்படாத", "தெரியாத"],
}
FACILITY_TYPES_LEX: dict[str, list[str]] = {
    "refinery": ["refiner", "oil refiner", "रिफाइनरी", "रिफायनरी", "तेलशोधक", "तेल शोधन", "refinery",
                 "சுத்திகரிப்பு", "ரிஃபைனரி", "ரிபைனரி", "எண்ணெய் சுத்திகரிப்பு"],
    "steel_plant": ["steel", "iron and steel", "इस्पात", "स्टील", "steel", "எஃகு", "ஸ்டீல்", "இரும்பு"],
    "thermal_power_plant": ["power plant", "power station", "thermal plant", "thermal power", "power",
                            "बिजली घर", "बिजलीघर", "बिजली संयंत्र", "पावर प्लांट", "पावर स्टेशन", "बिजली", "bijli", "power plant",
                            "மின் நிலைய", "மின்நிலைய", "அனல் மின்", "பவர் பிளான்ட்", "பவர் பிளாண்ட்", "மின்சார", "min nilaiyam"],
    "cement_plant": ["cement", "सीमेंट", "सिमेंट", "cement", "சிமெண்ட்", "சிமென்ட்"],
    "mining": ["mine", "mining", "quarr", "colliery", "coal mine", "खदान", "खान", "माइन", "खनन", "khadan", "khan",
               "சுரங்க", "குவாரி", "surangam"],
    "brick_kiln": ["brick", "kiln", "ईंट", "भट्टा", "भट्ठा", "भट्टे", "bhatta", "int bhatta", "செங்கல்", "சூளை", "chengal", "soolai"],
    "chemical_plant": ["chemical", "fertiliser", "fertilizer", "रसायन", "केमिकल", "उर्वरक", "rasayan",
                       "ரசாயன", "கெமிக்கல்", "உரம்", "உர ஆலை", "rasayana"],
    "lng_terminal": ["lng", "एलएनजी", "எல்என்ஜி"],
    "oil_gas_facility": ["oil and gas", "oil & gas", "oilfield", "oil field", "gas field", "तेल क्षेत्र", "तेल और गैस",
                         "எண்ணெய் வயல்", "எண்ணெய் மற்றும் எரிவாயு"],
    "metal_smelter": ["smelter", "aluminium", "aluminum", "foundry", "copper", "zinc", "स्मेल्टर", "एल्युमिनियम",
                      "உருக்காலை", "அலுமினிய"],
    "petrochemical": ["petrochem", "पेट्रोकेमिकल", "பெட்ரோகெமிக்கல்", "பெட்ரோ ரசாயன"],
}
PERSISTENCE_LEX: dict[str, list[str]] = {
    "persistent": ["persistent", "continuous", "constant", "always burning", "permanent", "लगातार", "स्थायी", "निरंतर",
                   "lagatar", "lagaataar", "sthayi", "தொடர்ச்சியான", "தொடர்ந்து", "நிலையான", "thodarchiyaana", "thodarndhu"],
    "recurring": ["recurring", "repeated", "repeating", "बार-बार", "बार बार", "baar baar", "மீண்டும் மீண்டும்", "திரும்பத் திரும்ப"],
}
DAYNIGHT: dict[str, list[str]] = {
    "N": ["night", "nighttime", "night-time", "at night", "रात", "रात्रि", "raat", "rat ko", "இரவு", "இரவில்", "iravu", "iravil"],
    "D": ["daytime", "day time", "during the day", "दिन में", "दिन के समय", "din mein", "din me", "பகல்", "பகலில்", "pagal", "pagalil"],
}
BASEMAP: dict[str, list[str]] = {
    "satellite": ["satellite", "imagery", "उपग्रह", "सैटेलाइट", "satellite", "செயற்கைக்கோள்", "சாட்டிலைட்", "சேட்டிலைட்"],
    "map": ["map view", "street map", "normal map", "road map", "plain map", "नक्शा", "मैप व्यू", "सामान्य नक्शा",
            "வரைபட காட்சி", "வரைபடக் காட்சி", "சாதாரண வரைபட"],
}
PAGES: dict[str, list[str]] = {
    "/dashboard": ["dashboard", "home", "main screen", "map page", "डैशबोर्ड", "होम", "मुख्य", "முகப்பு", "டாஷ்போர்டு", "டாஷ்போர்ட்"],
    "/incidents": ["incidents page", "incident page", "incidents list", "घटनाएं पेज", "சம்பவங்கள் பக்க"],
    "/alerts": ["alerts page", "alert centre", "alert center", "alert page", "अलर्ट पेज", "अलर्ट सेंटर", "எச்சரிக்கை பக்க", "எச்சரிக்கை மைய"],
    "/facilities": ["facilities page", "facility page", "facility list", "सुविधाएं पेज", "தொழிற்சாலைகள் பக்க"],
    "/thermal-sources": ["thermal sources", "sources page", "persistent sources", "ताप स्रोत पेज", "வெப்ப மூலங்கள் பக்க"],
    "/analytics": ["analytics", "charts", "graphs", "statistics", "stats", "trends", "विश्लेषण", "एनालिटिक्स", "आंकड़े",
                   "आँकड़े", "चार्ट", "ग्राफ", "பகுப்பாய்வு", "புள்ளிவிவர", "சார்ட்", "கிராஃப்", "analytics"],
    "/settings": ["settings", "system health", "health", "configuration", "सेटिंग्स", "सेटिंग", "सिस्टम", "अमेज़",
                  "அமைப்புகள்", "செட்டிங்ஸ்", "அமைப்பு நிலை", "settings"],
}
# "view" / "दृश्य" / "காட்சி" after a basemap name carry no meaning of their own.
VIEW_WORDS = ["view", "mode", "layer", "दृश्य", "व्यू", "मोड", "காட்சி", "வியூ", "மோட்"]
# Words that only indicate *where* (the next unknown words name a place).
PLACE_CUES = [
    "in", "at", "near", "around", "inside", "within", "over", "across", "from", "to", "of",
    "में", "मे", "पर", "के पास", "पास", "नजदीक", "आसपास", "के आसपास", "mein", "me", "par", "paas", "ke paas", "aas paas",
    "அருகில்", "அருகே", "பக்கத்தில்", "பகுதியில்", "la", "le", "il", "kitta", "pakkathula", "arugil",
]
# Filler words in the three languages (removed before looking for a place or facility name).
STOPWORDS = set(
    """
    number no num नंबर संख्या எண் सी सा से कौन कौनसी which one
    the a an me my us our all of for please pls can could would will you your i we want wanna need see give tell let lets
    is are was were be been being there here what which where when who whose how many much now currently right just only
    any some with and or on in at near around inside within over across from to into by this that these those it its them
    they do does did have has had show display list view find get bring up look go take zoom fly pan centre center focus
    open navigate switch page screen tab happening going detected recorded reported active current thermal events event
    data about more most than kindly hey hi hello ok okay thanks thank yes no today yesterday last past recent next
    area region zone places place location locations state city district side part map view
    मुझे मेरे मेरी का की के को में मे पर से और या है हैं था थे क्या कौन कौनसा कौनसी कहाँ कहां कैसे सभी सब अभी यह वह ये वो
    जी जरा ज़रा कृपया वाला वाले वाली जो हुई हुए हुआ रहा रही रहे हो ना तो भी कुछ कोई एक इस उस इन उन वाला दीजिए दो करो कर
    mujhe mere meri ka ki ke ko mein me par se aur ya hai hain tha kya kaun kahan kaise sab abhi yeh ye woh wo ji zara
    kripya wala wale wali jo hui hue hua raha rahi rahe ho na to bhi kuch koi ek is us karo kar do dijiye
    எனக்கு என் ஒரு இந்த அந்த உள்ள உள்ளன உள்ளது இருக்கும் இருக்கிறது இருக்கு இருக்குது என்ன எந்த எது எங்கே எல்லா அனைத்து
    இப்போது தயவுசெய்து கொஞ்சம் மற்றும் அல்லது பற்றி உடன் வேண்டும் தான் ஆன ஆகும் செய் பண்ணு
    enakku en oru indha intha andha antha ulla irukku irukkuthu enna endha edhu enge ella ellam ippo konjam thayavu seithu
    venum than pannu sei la le il kitta
    """.split()
)

# --------------------------------------------------------------------------- numbers and time
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "a": 1, "an": 1,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "पंद्रह": 15, "बीस": 20, "तीस": 30,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5, "panch": 5, "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "ஒன்று": 1, "ஒரு": 1, "இரண்டு": 2, "ரெண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5, "ஆறு": 6, "ஏழு": 7,
    "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10, "பதினைந்து": 15, "இருபது": 20, "முப்பது": 30,
    "ondru": 1, "rendu": 2, "moonu": 3, "naalu": 4, "anju": 5, "aaru": 6, "ezhu": 7, "ettu": 8, "onbadhu": 9, "pathu": 10,
}
TIME_UNITS = {
    "hour": 1, "hours": 1, "hr": 1, "hrs": 1, "h": 1, "घंटे": 1, "घंटा": 1, "घंटों": 1, "ghante": 1, "ghanta": 1,
    "மணி": 1, "மணிநேர": 1, "mani": 1,
    "day": 24, "days": 24, "दिन": 24, "दिनों": 24, "din": 24, "dino": 24, "நாள்": 24, "நாட்கள்": 24, "நாட்களில்": 24,
    "நாளில்": 24, "naal": 24, "naatkal": 24,
    "week": 168, "weeks": 168, "हफ्ते": 168, "हफ्ता": 168, "हफ़्ते": 168, "सप्ताह": 168, "hafte": 168, "hafta": 168,
    "வாரம்": 168, "வாரத்தில்": 168, "வாரங்கள்": 168, "vaaram": 168,
    "month": 720, "months": 720, "महीने": 720, "महीना": 720, "mahine": 720, "mahina": 720, "மாதம்": 720, "மாதத்தில்": 720, "maatham": 720,
}
TIME_PHRASES = {
    24: ["today", "past day", "last day", "24 hours", "आज", "aaj", "இன்று", "இன்றைக்கு", "indru", "inniku"],
    48: ["yesterday", "since yesterday", "two days", "कल से", "कल", "நேற்று", "netru", "nethu"],
    168: ["this week", "past week", "last week", "a week", "इस हफ्ते", "पिछले हफ्ते", "इस सप्ताह", "is hafte", "pichle hafte",
          "இந்த வாரம்", "கடந்த வாரம்", "indha vaaram", "kadantha vaaram"],
    720: ["this month", "past month", "last month", "इस महीने", "पिछले महीने", "is mahine", "இந்த மாதம்", "கடந்த மாதம்"],
}

# --------------------------------------------------------------------------- gazetteer (Indian states / UTs / major cities)
# name -> surface forms in English, Hindi, Tamil and common romanisations. Geocoded with the English name.
PLACES: dict[str, list[str]] = {
    # states
    "Andhra Pradesh": ["andhra pradesh", "andhra", "आंध्र प्रदेश", "आंध्र", "ஆந்திரப் பிரதேச", "ஆந்திர"],
    "Arunachal Pradesh": ["arunachal", "अरुणाचल", "அருணாசல", "அருணாச்சல"],
    "Assam": ["assam", "असम", "அசாம்", "அஸ்ஸாம்"],
    "Bihar": ["bihar", "बिहार", "பீகார்"],
    "Chhattisgarh": ["chhattisgarh", "chattisgarh", "छत्तीसगढ़", "छत्तीसगढ", "சத்தீஸ்கர்", "சத்தீஸ்கட்"],
    "Goa": ["goa", "गोवा", "கோவா"],
    "Gujarat": ["gujarat", "गुजरात", "குஜராத்"],
    "Haryana": ["haryana", "हरियाणा", "ஹரியானா", "அரியானா"],
    "Himachal Pradesh": ["himachal", "हिमाचल", "இமாச்சல", "ஹிமாச்சல"],
    "Jharkhand": ["jharkhand", "झारखंड", "झारखण्ड", "ஜார்கண்ட்", "ஜார்க்கண்ட்"],
    "Karnataka": ["karnataka", "कर्नाटक", "கர்நாடக"],
    "Kerala": ["kerala", "केरल", "கேரள"],
    "Madhya Pradesh": ["madhya pradesh", "mp state", "मध्य प्रदेश", "மத்தியப் பிரதேச", "மத்திய பிரதேச"],
    "Maharashtra": ["maharashtra", "महाराष्ट्र", "மகாராஷ்டிர", "மஹாராஷ்டிர"],
    "Manipur": ["manipur", "मणिपुर", "மணிப்பூர்"],
    "Meghalaya": ["meghalaya", "मेघालय", "மேகாலய"],
    "Mizoram": ["mizoram", "मिज़ोरम", "मिजोरम", "மிசோரம்"],
    "Nagaland": ["nagaland", "नागालैंड", "நாகாலாந்து"],
    "Odisha": ["odisha", "orissa", "ओडिशा", "उड़ीसा", "उडीसा", "ஒடிசா", "ஒரிசா"],
    "Punjab": ["punjab", "पंजाब", "பஞ்சாப்"],
    "Rajasthan": ["rajasthan", "राजस्थान", "ராஜஸ்தான்", "இராஜஸ்தான்"],
    "Sikkim": ["sikkim", "सिक्किम", "சிக்கிம்"],
    "Tamil Nadu": ["tamil nadu", "tamilnadu", "तमिलनाडु", "तमिल नाडु", "தமிழ்நாடு", "தமிழ்நாட்", "தமிழ் நாடு", "தமிழ் நாட்", "தமிழகம்", "தமிழகத்", "tamizh nadu"],
    "Telangana": ["telangana", "तेलंगाना", "தெலங்கானா", "தெலுங்கானா"],
    "Tripura": ["tripura", "त्रिपुरा", "திரிபுரா"],
    "Uttar Pradesh": ["uttar pradesh", "up state", "उत्तर प्रदेश", "உத்தரப் பிரதேச", "உத்தர பிரதேச"],
    "Uttarakhand": ["uttarakhand", "उत्तराखंड", "उत्तराखण्ड", "உத்தரகாண்ட்"],
    "West Bengal": ["west bengal", "bengal", "पश्चिम बंगाल", "बंगाल", "மேற்கு வங்க", "வங்காள"],
    # union territories
    "Delhi": ["delhi", "new delhi", "दिल्ली", "नई दिल्ली", "டெல்லி", "தில்லி", "புது டெல்லி"],
    "Jammu and Kashmir": ["jammu and kashmir", "jammu", "kashmir", "जम्मू", "कश्मीर", "ஜம்மு", "காஷ்மீர்"],
    "Ladakh": ["ladakh", "लद्दाख", "லடாக்"],
    "Puducherry": ["puducherry", "pondicherry", "पुडुचेरी", "புதுச்சேரி", "பாண்டிச்சேரி"],
    "Chandigarh": ["chandigarh", "चंडीगढ़", "चंडीगढ", "சண்டிகர்"],
    "Andaman and Nicobar Islands": ["andaman", "nicobar", "अंडमान", "அந்தமான்"],
    "Lakshadweep": ["lakshadweep", "लक्षद्वीप", "லட்சத்தீவு"],
    "Dadra and Nagar Haveli and Daman and Diu": ["daman", "diu", "dadra", "दमन", "தமன்"],
    # major cities / industrial hubs
    "Chennai": ["chennai", "madras", "चेन्नई", "चेन्नै", "मद्रास", "சென்னை", "சென்னைய", "மெட்ராஸ்"],
    "Mumbai": ["mumbai", "bombay", "मुंबई", "मुम्बई", "மும்பை"],
    "Kolkata": ["kolkata", "calcutta", "कोलकाता", "கொல்கத்தா"],
    "Bengaluru": ["bengaluru", "bangalore", "बेंगलुरु", "बंगलौर", "பெங்களூர்", "பெங்களூரு"],
    "Hyderabad": ["hyderabad", "हैदराबाद", "ஹைதராபாத்", "ஐதராபாத்"],
    "Ahmedabad": ["ahmedabad", "अहमदाबाद", "அகமதாபாத்"],
    "Pune": ["pune", "पुणे", "புனே"],
    "Jaipur": ["jaipur", "जयपुर", "ஜெய்ப்பூர்"],
    "Lucknow": ["lucknow", "लखनऊ", "லக்னோ"],
    "Kanpur": ["kanpur", "कानपुर", "கான்பூர்"],
    "Nagpur": ["nagpur", "नागपुर", "நாக்பூர்"],
    "Patna": ["patna", "पटना", "பாட்னா"],
    "Bhopal": ["bhopal", "भोपाल", "போபால்"],
    "Indore": ["indore", "इंदौर", "இந்தூர்"],
    "Surat": ["surat", "सूरत", "சூரத்"],
    "Vadodara": ["vadodara", "baroda", "वडोदरा", "வதோதரா"],
    "Jamnagar": ["jamnagar", "जामनगर", "ஜாம்நகர்"],
    "Visakhapatnam": ["visakhapatnam", "vizag", "विशाखापत्तनम", "விசாகப்பட்டினம்"],
    "Bhubaneswar": ["bhubaneswar", "भुवनेश्वर", "புவனேஸ்வர்"],
    "Raipur": ["raipur", "रायपुर", "ராய்ப்பூர்"],
    "Ranchi": ["ranchi", "रांची", "ராஞ்சி"],
    "Dhanbad": ["dhanbad", "धनबाद", "தன்பாத்"],
    "Jamshedpur": ["jamshedpur", "जमशेदपुर", "ஜம்ஷெட்பூர்"],
    "Bokaro": ["bokaro", "बोकारो", "பொகாரோ"],
    "Korba": ["korba", "कोरबा", "கோர்பா"],
    "Raigarh": ["raigarh", "रायगढ़", "ராய்கர்"],
    "Angul": ["angul", "अंगुल", "அங்குல்"],
    "Rourkela": ["rourkela", "राउरकेला", "ரூர்கேலா"],
    "Durgapur": ["durgapur", "दुर्गापुर", "துர்காபூர்"],
    "Asansol": ["asansol", "आसनसोल", "அசன்சோல்"],
    "Singrauli": ["singrauli", "सिंगरौली", "சிங்ரௌலி"],
    "Bellary": ["bellary", "ballari", "बेल्लारी", "பெல்லாரி"],
    "Coimbatore": ["coimbatore", "कोयंबटूर", "கோயம்புத்தூர்", "கோவை"],
    "Madurai": ["madurai", "मदुरै", "மதுரை"],
    "Tiruchirappalli": ["trichy", "tiruchirappalli", "तिरुचिरापल्ली", "திருச்சி", "திருச்சிராப்பள்ளி"],
    "Salem": ["salem", "सेलम", "சேலம்"],
    "Tuticorin": ["tuticorin", "thoothukudi", "तूतीकोरिन", "தூத்துக்குடி"],
    "Neyveli": ["neyveli", "नेवेली", "நெய்வேலி"],
    "Mettur": ["mettur", "मेट्टूर", "மேட்டூர்"],
    "Ennore": ["ennore", "एन्नोर", "எண்ணூர்"],
    "Kochi": ["kochi", "cochin", "कोच्चि", "கொச்சி"],
    "Mangaluru": ["mangalore", "mangaluru", "मंगलुरु", "मैंगलोर", "மங்களூர்"],
    "Bathinda": ["bathinda", "भटिंडा", "பதிண்டா"],
    "Panipat": ["panipat", "पानीपत", "பானிபட்"],
    "Mathura": ["mathura", "मथुरा", "மதுரா"],
    "Barmer": ["barmer", "बाड़मेर", "बाडमेर", "பார்மர்"],
    "Guwahati": ["guwahati", "गुवाहाटी", "குவஹாத்தி", "கௌஹாத்தி"],
    "Haldia": ["haldia", "हल्दिया", "ஹால்டியா"],
    "Paradip": ["paradip", "paradeep", "पारादीप", "பாரதீப்"],
    "Mumbai High": ["mumbai high", "bombay high", "मुंबई हाई", "மும்பை ஹை"],
}

# --------------------------------------------------------------------------- localised output
LANGS = ("en", "hi", "ta")

PRIORITY_TEXT = {
    "en": {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"},
    "hi": {"critical": "गंभीर", "high": "उच्च", "medium": "मध्यम", "low": "निम्न"},
    "ta": {"critical": "மிக அவசரம்", "high": "உயர்", "medium": "நடுத்தர", "low": "குறைந்த"},
}
PRIORITY_MIN_TEXT = {"en": "{p}+ priority", "hi": "{p} या अधिक प्राथमिकता", "ta": "{p} அல்லது அதிக முன்னுரிமை"}
CLASS_TEXT = {
    "hi": {
        "gas_flare_like": "गैस फ्लेयर जैसी गतिविधि", "mining_associated": "खनन से जुड़ी गतिविधि",
        "persistent_industrial_source": "लगातार औद्योगिक ताप स्रोत", "industrial_associated_event": "औद्योगिक ताप घटना",
        "persistent_unattributed_source": "लगातार ताप स्रोत (कोई मानचित्रित सुविधा नहीं)",
        "agricultural_burning": "संभावित फसल/पराली दहन", "vegetation_fire": "संभावित जंगल की आग",
        "unclassified_anomaly": "अवर्गीकृत ताप विसंगति", "industrial": "औद्योगिक",
    },
    "ta": {
        "gas_flare_like": "வாயு எரிப்பு போன்ற செயல்பாடு", "mining_associated": "சுரங்கம் சார்ந்த செயல்பாடு",
        "persistent_industrial_source": "தொடர்ச்சியான தொழில்துறை வெப்ப மூலம்", "industrial_associated_event": "தொழில்துறை வெப்ப நிகழ்வு",
        "persistent_unattributed_source": "தொடர்ச்சியான வெப்ப மூலம் (வரைபடத்தில் ஆலை இல்லை)",
        "agricultural_burning": "சாத்தியமான பயிர் எரிப்பு", "vegetation_fire": "சாத்தியமான காட்டுத் தீ",
        "unclassified_anomaly": "வகைப்படுத்தப்படாத வெப்ப முரண்பாடு", "industrial": "தொழில்துறை",
    },
}
FACILITY_TEXT = {
    "hi": {
        "refinery": "रिफाइनरी", "steel_plant": "इस्पात संयंत्र", "thermal_power_plant": "ताप विद्युत संयंत्र",
        "cement_plant": "सीमेंट संयंत्र", "mining": "खनन क्षेत्र", "brick_kiln": "ईंट भट्ठा", "chemical_plant": "रसायन संयंत्र",
        "lng_terminal": "एलएनजी टर्मिनल", "oil_gas_facility": "तेल व गैस सुविधा", "metal_smelter": "धातु प्रगलन संयंत्र",
        "petrochemical": "पेट्रोकेमिकल संयंत्र", "gas_flare": "गैस फ्लेयर", "industrial_works": "औद्योगिक इकाई",
    },
    "ta": {
        "refinery": "சுத்திகரிப்பு ஆலை", "steel_plant": "எஃகு ஆலை", "thermal_power_plant": "அனல் மின் நிலையம்",
        "cement_plant": "சிமெண்ட் ஆலை", "mining": "சுரங்கப் பகுதி", "brick_kiln": "செங்கல் சூளை", "chemical_plant": "ரசாயன ஆலை",
        "lng_terminal": "எல்என்ஜி முனையம்", "oil_gas_facility": "எண்ணெய்-எரிவாயு நிலையம்", "metal_smelter": "உலோக உருக்காலை",
        "petrochemical": "பெட்ரோகெமிக்கல் ஆலை", "gas_flare": "வாயு எரிப்பு", "industrial_works": "தொழிற்சாலை",
    },
}
PAGE_TEXT = {
    "en": {"/dashboard": "the dashboard", "/incidents": "incidents", "/alerts": "the alert centre", "/facilities": "facilities",
           "/thermal-sources": "thermal sources", "/analytics": "analytics", "/settings": "settings & system health"},
    "hi": {"/dashboard": "डैशबोर्ड", "/incidents": "घटनाएं", "/alerts": "अलर्ट केंद्र", "/facilities": "औद्योगिक सुविधाएं",
           "/thermal-sources": "ताप स्रोत", "/analytics": "विश्लेषण", "/settings": "सेटिंग्स व सिस्टम स्थिति"},
    "ta": {"/dashboard": "டாஷ்போர்டு", "/incidents": "சம்பவங்கள்", "/alerts": "எச்சரிக்கை மையம்", "/facilities": "தொழிற்சாலைகள்",
           "/thermal-sources": "வெப்ப மூலங்கள்", "/analytics": "பகுப்பாய்வு", "/settings": "அமைப்புகள் மற்றும் கணினி நிலை"},
}
THING_TEXT = {
    "en": {"incidents": "incidents", "alerts": "alerts", "sources": "thermal sources", "facilities": "facilities", "detections": "thermal detections"},
    "hi": {"incidents": "घटनाएं", "alerts": "अलर्ट", "sources": "ताप स्रोत", "facilities": "औद्योगिक सुविधाएं", "detections": "ताप डिटेक्शन"},
    "ta": {"incidents": "சம்பவங்கள்", "alerts": "எச்சரிக்கைகள்", "sources": "வெப்ப மூலங்கள்", "facilities": "தொழிற்சாலைகள்", "detections": "வெப்பக் கண்டறிதல்கள்"},
}
NIGHT_TEXT = {"en": {"N": "at night", "D": "during the day"}, "hi": {"N": "रात में", "D": "दिन में"}, "ta": {"N": "இரவில்", "D": "பகலில்"}}
PERSIST_TEXT = {
    "en": {"persistent": "persistent", "recurring": "recurring"},
    "hi": {"persistent": "लगातार", "recurring": "बार-बार होने वाले"},
    "ta": {"persistent": "தொடர்ச்சியான", "recurring": "மீண்டும் நிகழும்"},
}
NEAR_TEXT = {"en": "near {x}", "hi": "{x} के पास", "ta": "{x} அருகில்"}
INDUSTRIAL_TEXT = {"en": "industrial", "hi": "औद्योगिक", "ta": "தொழில்துறை"}

def when_text(hours: int, lang: str) -> str:
    """'in the last 24 hours' in the chosen language."""
    if hours % 24 == 0 and hours >= 48:
        n = hours // 24
        return {"en": f"in the last {n} days", "hi": f"पिछले {n} दिनों में", "ta": f"கடந்த {n} நாட்களில்"}[lang]
    return {"en": f"in the last {hours} hours", "hi": f"पिछले {hours} घंटों में", "ta": f"கடந்த {hours} மணி நேரத்தில்"}[lang]


def area_text(place: str, lang: str) -> str:
    return {"en": f" in the {place} area", "hi": f" {place} क्षेत्र में", "ta": f" {place} பகுதியில்"}[lang]


T = {
    "help": {
        "en": "You can ask in your own words - about fires, incidents, alerts, facilities, places and time. For example:",
        "hi": "आप अपने शब्दों में पूछ सकते हैं - आग, घटनाएं, अलर्ट, कारखाने, जगह और समय के बारे में। उदाहरण:",
        "ta": "தீ, சம்பவங்கள், எச்சரிக்கைகள், ஆலைகள், இடம், நேரம் பற்றி உங்கள் சொந்த வார்த்தைகளில் கேட்கலாம். உதாரணம்:",
    },
    "forbidden": {
        "en": "I can only show and explain the monitoring data - I can't delete or change anything. Nothing was changed.",
        "hi": "मैं केवल निगरानी डेटा दिखा और समझा सकता हूँ - कुछ भी हटा या बदल नहीं सकता। कुछ भी नहीं बदला गया।",
        "ta": "நான் கண்காணிப்புத் தரவைக் காட்டவும் விளக்கவும் மட்டுமே முடியும் - எதையும் நீக்கவோ மாற்றவோ முடியாது. எதுவும் மாற்றப்படவில்லை.",
    },
    "unsupported": {
        "en": "Sorry, I could not understand that as a ThermoSentinel request. Nothing was changed. Try one of these:",
        "hi": "माफ़ कीजिए, मैं इसे समझ नहीं पाया। कुछ भी नहीं बदला गया। इनमें से कोई आज़माएं:",
        "ta": "மன்னிக்கவும், இதைப் புரிந்துகொள்ள முடியவில்லை. எதுவும் மாற்றப்படவில்லை. இவற்றில் ஒன்றை முயற்சிக்கவும்:",
    },
    "place_not_found": {
        "en": "I could not find “{place}” inside India's monitoring area.",
        "hi": "“{place}” भारत के निगरानी क्षेत्र में नहीं मिला।",
        "ta": "“{place}” இந்தியக் கண்காணிப்புப் பகுதியில் கிடைக்கவில்லை.",
    },
    "reset": {
        "en": "Filters cleared - showing all of India.",
        "hi": "फ़िल्टर हटा दिए गए - पूरा भारत दिखाया जा रहा है।",
        "ta": "வடிகட்டிகள் அழிக்கப்பட்டன - முழு இந்தியாவும் காட்டப்படுகிறது.",
    },
    "basemap_satellite": {"en": "Switched to satellite view.", "hi": "सैटेलाइट दृश्य चालू किया गया।", "ta": "செயற்கைக்கோள் காட்சிக்கு மாற்றப்பட்டது."},
    "basemap_map": {"en": "Switched to map view.", "hi": "मानचित्र दृश्य चालू किया गया।", "ta": "வரைபடக் காட்சிக்கு மாற்றப்பட்டது."},
    "open_page": {"en": "Opening {page}.", "hi": "{page} खोल रहा हूँ।", "ta": "{page} திறக்கப்படுகிறது."},
    "open_incident": {
        "en": "Opening incident {ref}: {title}.",
        "hi": "घटना {ref} खोल रहा हूँ: {title}।",
        "ta": "சம்பவம் {ref} திறக்கப்படுகிறது: {title}.",
    },
    "no_incident": {"en": "There is no incident number {id}.", "hi": "घटना संख्या {id} मौजूद नहीं है।", "ta": "சம்பவ எண் {id} இல்லை."},
    "no_alert": {"en": "There is no alert number {id}.", "hi": "अलर्ट संख्या {id} मौजूद नहीं है।", "ta": "எச்சரிக்கை எண் {id} இல்லை."},
    "open_alert": {
        "en": "Opening {severity} alert #{id}: {title}.",
        "hi": "{severity} अलर्ट #{id} खोल रहा हूँ: {title}।",
        "ta": "{severity} எச்சரிக்கை #{id} திறக்கப்படுகிறது: {title}.",
    },
    "latest_alert": {
        "en": "Opening the latest {severity} alert: {title}.",
        "hi": "नवीनतम {severity} अलर्ट खोल रहा हूँ: {title}।",
        "ta": "சமீபத்திய {severity} எச்சரிக்கை திறக்கப்படுகிறது: {title}.",
    },
    "no_alerts": {"en": "There are no alerts yet.", "hi": "अभी कोई अलर्ट नहीं है।", "ta": "இன்னும் எச்சரிக்கைகள் இல்லை."},
    "latest_event": {
        "en": "Zooming to the latest matching thermal event: {label}{at}.",
        "hi": "नवीनतम मिलती-जुलती ताप घटना पर ज़ूम कर रहा हूँ: {label}{at}।",
        "ta": "பொருந்தும் சமீபத்திய வெப்ப நிகழ்வு பெரிதாக்கப்படுகிறது: {label}{at}.",
    },
    "no_event": {
        "en": "No matching active thermal event is stored{scope}.",
        "hi": "कोई मिलती-जुलती सक्रिय ताप घटना दर्ज नहीं है{scope}।",
        "ta": "பொருந்தும் செயலில் உள்ள வெப்ப நிகழ்வு எதுவும் இல்லை{scope}.",
    },
    "hottest": {
        "en": "The most intense thermal event {when}{where}: {label}{at}, peak {frp} MW fire radiative power. Zooming there.",
        "hi": "{when}{where} सबसे तीव्र ताप घटना: {label}{at}, अधिकतम {frp} मेगावाट विकिरण शक्ति। वहाँ ज़ूम कर रहा हूँ।",
        "ta": "{when}{where} மிகத் தீவிரமான வெப்ப நிகழ்வு: {label}{at}, உச்ச {frp} மெகாவாட் கதிர்வீச்சு சக்தி. அங்கே பெரிதாக்கப்படுகிறது.",
    },
    "count_detections": {
        "en": "NASA FIRMS recorded {n} thermal detections{where} {when} ({night} at night).",
        "hi": "{when}{where} NASA FIRMS ने {n} ताप डिटेक्शन दर्ज किए ({night} रात में)।",
        "ta": "{when}{where} NASA FIRMS {n} வெப்பக் கண்டறிதல்களைப் பதிவு செய்தது (இரவில் {night}).",
    },
    "count_incidents": {"en": "Open incidents{desc}: {n}.", "hi": "खुली घटनाएं{desc}: {n}।", "ta": "திறந்த சம்பவங்கள்{desc}: {n}."},
    "count_alerts": {"en": "Open alerts{desc}: {n}.", "hi": "खुले अलर्ट{desc}: {n}।", "ta": "திறந்த எச்சரிக்கைகள்{desc}: {n}."},
    "count_sources": {
        "en": "Active persistent thermal sources{desc}: {n} ({ind} associated with mapped industrial facilities).",
        "hi": "सक्रिय लगातार ताप स्रोत{desc}: {n} ({ind} मानचित्रित औद्योगिक सुविधाओं से जुड़े)।",
        "ta": "செயலில் உள்ள தொடர்ச்சியான வெப்ப மூலங்கள்{desc}: {n} ({ind} தொழிற்சாலைகளுடன் தொடர்புடையவை).",
    },
    "count_facilities": {
        "en": "Monitored industrial facilities{desc}: {n}.",
        "hi": "निगरानी में औद्योगिक सुविधाएं{desc}: {n}।",
        "ta": "கண்காணிக்கப்படும் தொழிற்சாலைகள்{desc}: {n}.",
    },
    "zoom_place": {
        "en": "Zooming to {place}: {n} thermal detections and {inc} open incidents in this area {when}.",
        "hi": "{place} पर ज़ूम कर रहा हूँ: {when} इस क्षेत्र में {n} ताप डिटेक्शन और {inc} खुली घटनाएं।",
        "ta": "{place} பெரிதாக்கப்படுகிறது: {when} இந்தப் பகுதியில் {n} வெப்பக் கண்டறிதல்கள், {inc} திறந்த சம்பவங்கள்.",
    },
    "show_list": {"en": "Showing {n} {things}{desc}.", "hi": "{things}{desc} दिखा रहा हूँ: {n}।", "ta": "{things}{desc} காட்டப்படுகிறது: {n}."},
    "show_map": {
        "en": "Showing {desc} on the map: {n} thermal detections {when}.",
        "hi": "मानचित्र पर {desc} दिखा रहा हूँ: {when} {n} ताप डिटेक्शन।",
        "ta": "வரைபடத்தில் {desc} காட்டப்படுகிறது: {when} {n} வெப்பக் கண்டறிதல்கள்.",
    },
    "facility_zoom": {
        "en": "Zooming to {name} ({type}).",
        "hi": "{name} ({type}) पर ज़ूम कर रहा हूँ।",
        "ta": "{name} ({type}) பெரிதாக்கப்படுகிறது.",
    },
    "briefing": {
        "en": None,  # English uses the full briefing text
        "hi": ("स्थिति सारांश: {when} NASA FIRMS ने {det} ताप डिटेक्शन दर्ज किए। {clusters} सक्रिय क्लस्टर हैं, जिनमें {ind} "
               "औद्योगिक सुविधाओं से जुड़े और {pers} लगातार सक्रिय हैं। {open} खुली घटनाएं हैं: {c} गंभीर, {h} उच्च, {m} मध्यम। "
               "{alerts} अलर्ट पुष्टि की प्रतीक्षा में हैं। वर्गीकरण उपग्रह और खुले भू-स्थानिक डेटा से अनुमानित है और सत्यापन आवश्यक है।"),
        "ta": ("நிலைமை சுருக்கம்: {when} NASA FIRMS {det} வெப்பக் கண்டறிதல்களைப் பதிவு செய்தது. {clusters} செயலில் உள்ள தொகுப்புகள் "
               "உள்ளன; அவற்றில் {ind} தொழிற்சாலைகளுடன் தொடர்புடையவை, {pers} தொடர்ந்து செயல்படுகின்றன. {open} திறந்த சம்பவங்கள்: "
               "{c} மிக அவசரம், {h} உயர், {m} நடுத்தர. {alerts} எச்சரிக்கைகள் உறுதிப்படுத்தலுக்குக் காத்திருக்கின்றன. வகைப்பாடுகள் "
               "செயற்கைக்கோள் மற்றும் திறந்த புவியியல் தரவிலிருந்து ஊகிக்கப்பட்டவை; சரிபார்ப்பு தேவை."),
    },
}
LABELS = {
    "count": {"en": "Count", "hi": "गिनती", "ta": "எண்ணிக்கை"},
    "show": {"en": "Show", "hi": "दिखाएं", "ta": "காட்டு"},
    "zoom": {"en": "Zoom to", "hi": "ज़ूम करें", "ta": "பெரிதாக்கு"},
    "open": {"en": "Open", "hi": "खोलें", "ta": "திற"},
    "brief": {"en": "Situation briefing", "hi": "स्थिति सारांश", "ta": "நிலைமை சுருக்கம்"},
    "help": {"en": "Help", "hi": "मदद", "ta": "உதவி"},
    "reset": {"en": "Clear filters", "hi": "फ़िल्टर हटाएं", "ta": "வடிகட்டிகளை அழி"},
    "basemap": {"en": "Change map view", "hi": "मानचित्र दृश्य बदलें", "ta": "வரைபடக் காட்சியை மாற்று"},
    "latest": {"en": "Latest", "hi": "नवीनतम", "ta": "சமீபத்திய"},
    "hottest": {"en": "Most intense event", "hi": "सबसे तीव्र घटना", "ta": "மிகத் தீவிரமான நிகழ்வு"},
    "unsupported": {"en": "Not understood", "hi": "समझ नहीं आया", "ta": "புரியவில்லை"},
    "forbidden": {"en": "Not allowed (read-only)", "hi": "अनुमति नहीं (केवल पढ़ने के लिए)", "ta": "அனுமதி இல்லை (படிக்க மட்டும்)"},
}
EXAMPLES = {
    "en": [
        "Show fires in Chennai today",
        "How many high priority incidents are there?",
        "Show gas flares at night in the last week",
        "Which is the biggest fire in Odisha?",
        "Show steel plants in Jharkhand",
        "Open the latest alert",
        "Switch to satellite view",
        "Give me a briefing",
    ],
    "hi": [
        "आज चेन्नई में आग दिखाओ",
        "कितनी उच्च प्राथमिकता वाली घटनाएं हैं?",
        "पिछले हफ्ते रात में गैस फ्लेयर दिखाओ",
        "ओडिशा में सबसे बड़ी आग कौन सी है?",
        "झारखंड में स्टील प्लांट दिखाओ",
        "नवीनतम अलर्ट खोलो",
        "सैटेलाइट दृश्य दिखाओ",
        "स्थिति का सारांश बताओ",
    ],
    "ta": [
        "இன்று சென்னையில் தீயைக் காட்டு",
        "எத்தனை உயர் முன்னுரிமை சம்பவங்கள் உள்ளன?",
        "கடந்த வாரம் இரவில் வாயு எரிப்பைக் காட்டு",
        "ஒடிசாவில் மிகப்பெரிய தீ எது?",
        "ஜார்கண்டில் எஃகு ஆலைகளைக் காட்டு",
        "சமீபத்திய எச்சரிக்கையைத் திற",
        "செயற்கைக்கோள் காட்சியைக் காட்டு",
        "நிலைமை சுருக்கம் சொல்",
    ],
}
