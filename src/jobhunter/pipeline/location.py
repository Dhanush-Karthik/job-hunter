"""Location parsing: canonical Indian city, state-level locations, pan-India, foreign regions, remote hints.

`parse_location` never guesses a city: Indeed's "TN, India" yields city=None, state="TN" (caller tags it
"city unknown: TN"). Unrecognised free text yields city=None, state=None and no foreign marker, which the
prefilter lets through with a tag (recall first).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# canonical city -> (state code, lowercase aliases). Target cities first; the rest only exist so the
# prefilter can name the city it drops ("location: Pune").
CITIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "Chennai": ("TN", ("chennai", "madras")),
    "Bengaluru": ("KA", ("bengaluru", "bangalore", "bengalooru")),
    "Pune": ("MH", ("pune",)),
    "Mumbai": ("MH", ("mumbai", "navi mumbai", "thane", "bombay")),
    "Nagpur": ("MH", ("nagpur",)),
    "Nashik": ("MH", ("nashik",)),
    "Hyderabad": ("TS", ("hyderabad", "secunderabad", "hitec city")),
    "Delhi": ("DL", ("delhi", "new delhi")),
    "Gurugram": ("HR", ("gurugram", "gurgaon")),
    "Faridabad": ("HR", ("faridabad",)),
    "Noida": ("UP", ("noida", "greater noida")),
    "Ghaziabad": ("UP", ("ghaziabad",)),
    "Lucknow": ("UP", ("lucknow",)),
    "Kolkata": ("WB", ("kolkata", "calcutta")),
    "Ahmedabad": ("GJ", ("ahmedabad",)),
    "Gandhinagar": ("GJ", ("gandhinagar",)),
    "Vadodara": ("GJ", ("vadodara", "baroda")),
    "Surat": ("GJ", ("surat",)),
    "Kochi": ("KL", ("kochi", "cochin", "kakkanad")),
    "Thiruvananthapuram": ("KL", ("thiruvananthapuram", "trivandrum", "technopark")),
    "Kozhikode": ("KL", ("kozhikode", "calicut")),
    "Coimbatore": ("TN", ("coimbatore",)),
    "Madurai": ("TN", ("madurai",)),
    "Tiruchirappalli": ("TN", ("tiruchirappalli", "trichy")),
    "Hosur": ("TN", ("hosur",)),
    "Mysuru": ("KA", ("mysuru", "mysore")),
    "Mangaluru": ("KA", ("mangaluru", "mangalore")),
    "Hubballi": ("KA", ("hubballi", "hubli")),
    "Jaipur": ("RJ", ("jaipur",)),
    "Chandigarh": ("CH", ("chandigarh",)),
    "Mohali": ("PB", ("mohali",)),
    "Indore": ("MP", ("indore",)),
    "Bhopal": ("MP", ("bhopal",)),
    "Bhubaneswar": ("OD", ("bhubaneswar",)),
    "Visakhapatnam": ("AP", ("visakhapatnam", "vizag")),
    "Vijayawada": ("AP", ("vijayawada",)),
    "Patna": ("BR", ("patna",)),
    "Ranchi": ("JH", ("ranchi",)),
    "Guwahati": ("AS", ("guwahati",)),
    "Dehradun": ("UT", ("dehradun",)),
    "Raipur": ("CG", ("raipur",)),
    "Puducherry": ("PY", ("puducherry", "pondicherry")),
    "Goa": ("GA", ("panaji",)),
}
CITY_STATE = {city: st for city, (st, _) in CITIES.items()}
_ALIAS_TO_CITY = {a: city for city, (_, aliases) in CITIES.items() for a in aliases}
_CITY_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _ALIAS_TO_CITY), key=len, reverse=True)) + r")\b")

STATE_NAMES = {
    "tamil nadu": "TN", "karnataka": "KA", "maharashtra": "MH", "telangana": "TS", "andhra pradesh": "AP",
    "kerala": "KL", "gujarat": "GJ", "haryana": "HR", "uttar pradesh": "UP", "west bengal": "WB",
    "rajasthan": "RJ", "madhya pradesh": "MP", "punjab": "PB", "odisha": "OD", "orissa": "OD",
    "bihar": "BR", "jharkhand": "JH", "assam": "AS", "uttarakhand": "UT", "chhattisgarh": "CG",
    "goa": "GA", "himachal pradesh": "HP", "puducherry": "PY", "jammu and kashmir": "JK",
}
_STATE_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, STATE_NAMES), key=len, reverse=True)) + r")\b")
STATE_CODES = set(STATE_NAMES.values()) | {"DL", "CH"}
_STATE_CODE_ALIAS = {"TG": "TS"}  # Telangana's newer code
# States that contain a target city: a state-level posting there may well be in Chennai/Bengaluru.
TARGET_STATES = {"TN", "KA"}

_REGION_TERMS: dict[str, tuple[str, ...]] = {
    "us": ("united states", "usa", "america", "americas", "north america", "new york", "california",
           "san francisco", "texas", "seattle", "austin", "boston", "chicago", "atlanta", "new jersey",
           "florida", "colorado", "massachusetts"),
    "eu": ("europe", "european union", "emea", "united kingdom", "england", "london", "germany", "berlin",
           "munich", "france", "paris", "spain", "madrid", "barcelona", "portugal", "lisbon", "netherlands",
           "amsterdam", "ireland", "dublin", "poland", "warsaw", "sweden", "stockholm", "italy", "milan",
           "switzerland", "zurich", "belgium", "denmark", "finland", "norway", "austria", "vienna",
           "czech republic", "prague", "romania", "bulgaria", "greece", "estonia", "lithuania"),
    "other": ("canada", "toronto", "vancouver", "brazil", "mexico", "argentina", "colombia", "latam",
              "latin america", "south america", "australia", "sydney", "melbourne", "new zealand",
              "singapore", "malaysia", "kuala lumpur", "indonesia", "philippines", "manila", "vietnam",
              "thailand", "japan", "tokyo", "china", "hong kong", "korea", "dubai", "united arab emirates",
              "abu dhabi", "saudi arabia", "riyadh", "qatar", "doha", "kuwait", "bahrain", "oman", "israel",
              "turkey", "egypt", "nigeria", "kenya", "south africa", "africa", "middle east", "pakistan",
              "bangladesh", "sri lanka", "nepal"),
}
_REGION_OF = {t: region for region, terms in _REGION_TERMS.items() for t in terms}
_REGION_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _REGION_OF), key=len, reverse=True)) + r")\b")
# case-sensitive abbreviations (a lowercase "us" is just a pronoun)
_ABBR_RE = re.compile(r"\b(US|USA|U\.S\.A?\.?|UK|EU|UAE)(?![A-Za-z])")
_ABBR_REGION = {"US": "us", "USA": "us", "UK": "eu", "EU": "eu", "UAE": "other"}  # keys without dots

_APAC_RE = re.compile(r"\b(apac|asia[\s-]pacific|asia)\b", re.IGNORECASE)
_WORLD_RE = re.compile(r"\b(worldwide|world[\s-]wide|anywhere|globally|global|work from anywhere)\b", re.IGNORECASE)
_INDIA_RE = re.compile(r"\bindia\b", re.IGNORECASE)
_PAN_RE = re.compile(r"\bpan[\s-]?india\b|\banywhere in india\b|\ball[\s-]india\b|\bacross india\b", re.IGNORECASE)
_REMOTE_RE = re.compile(r"\bremote(?:ly)?\b|\bwork from home\b|\bwfh\b|\bwork from anywhere\b", re.IGNORECASE)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
_ONSITE_RE = re.compile(r"\bon[\s-]?site\b|\bwork from office\b|\bwfo\b", re.IGNORECASE)
_NOISE_RE = re.compile(r"\b(remote(?:ly)?|hybrid|on[\s-]?site|wfh|work from home|anywhere|in|within|across|"
                       r"all|pan|of|the|\d+\s*locations?)\b", re.IGNORECASE)


def canonical_city(name: str) -> str:
    """'Bangalore' / 'bengaluru urban' -> 'Bengaluru'; unknown names come back title-cased."""
    low = " ".join(name.lower().split())
    m = _CITY_RE.search(low)
    return _ALIAS_TO_CITY[m.group(1)] if m else name.strip().title()


@dataclass
class LocationInfo:
    raw: str | None
    city: str | None = None  # preferred city: first target city if any, else first city mentioned
    cities: list[str] = field(default_factory=list)  # every city mentioned, canonical, in order
    state: str | None = None  # state code, only when no city is known ("TN")
    pan_india: bool = False
    india: bool = False  # explicit India / Indian city / Indian state
    foreign: str | None = None  # display name of a non-India place, when there is no India signal
    region: str | None = None  # india | apac | us | eu | other | worldwide | None (remote scope hint)
    remote: bool = False
    hybrid: bool = False
    onsite: bool = False


def _foreign_hits(text: str) -> list[tuple[int, str, str]]:
    hits = [(m.start(), m.group(1), _REGION_OF[m.group(1)]) for m in _REGION_RE.finditer(text.lower())]
    hits += [(m.start(), m.group(1), _ABBR_REGION[m.group(1).replace(".", "")]) for m in _ABBR_RE.finditer(text)]
    return sorted(hits)


def parse_location(raw: str | None, targets: set[str] | frozenset[str] = frozenset()) -> LocationInfo:
    """`targets` = canonical target city names; the first one mentioned becomes `city`."""
    info = LocationInfo(raw=raw)
    if not raw or not raw.strip():
        return info
    text = " ".join(raw.split())
    low = text.lower()
    info.remote = bool(_REMOTE_RE.search(text))
    info.hybrid = bool(_HYBRID_RE.search(text))
    info.onsite = bool(_ONSITE_RE.search(text))
    india_word = bool(_INDIA_RE.search(text))

    for m in _CITY_RE.finditer(low):
        city = _ALIAS_TO_CITY[m.group(1)]
        if city not in info.cities:
            info.cities.append(city)
    foreign = _foreign_hits(text)
    if info.cities and not india_word and foreign and not any(c in targets for c in info.cities):
        info.cities = []  # "Salem, OR, United States": a US place that happens to share a city name
    if info.cities:
        info.city = next((c for c in info.cities if c in targets), info.cities[0])
        info.india = True
    else:
        for tok in re.split(r"[,/|;()\-–]", text):
            tok = tok.strip()
            code = _STATE_CODE_ALIAS.get(tok, tok)
            if india_word and code in STATE_CODES and tok.isupper():
                info.state, info.india = code, True
                break
        if info.state is None:
            m = _STATE_RE.search(low)
            if m:
                info.state, info.india = STATE_NAMES[m.group(1)], True
    if india_word:
        info.india = True
    if not info.india and foreign:
        info.foreign = foreign[0][1].upper() if len(foreign[0][1]) <= 3 else foreign[0][1].title()
    if (_PAN_RE.search(text) or _NOISE_RE.sub("", low).strip(" ,.-–/|()") == "india") and not info.cities:
        info.pan_india = True

    if info.india:
        info.region = "india"
    elif _APAC_RE.search(text):
        info.region = "apac"
    elif foreign:
        info.region = foreign[0][2]
    elif _WORLD_RE.search(text):
        info.region = "worldwide"
    return info
