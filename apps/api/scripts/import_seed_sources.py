"""Deterministic, idempotent importer for the gh-237 city-coverage seed sources.

Reads the provenance JSON under
``specs/gh-237-city-coverage-expansion/sources/`` (the six region city files and
``countries.json``) and renders the corresponding entries into the four data
modules ``app/data/{cities,hotels,places,tips}.py``.

Nothing is hand-typed: every rendered field originates from a source JSON value.
Provenance-only fields (``wikidata``, ``source_url``, ``evidence``,
``image_note``, ``status_reviewed``) are dropped. Hotel ``latitude``/``longitude``
(offline-required in the source, used only by the ``--online`` verifier) are also
dropped because the target ``HOTELS`` rows carry no coordinates; place
coordinates are kept.

Each generated span is wrapped in ``# BEGIN gh-237 <tag>`` / ``# END gh-237 <tag>``
marker comments. On every run the existing span is stripped and re-rendered from
the source, so a second run produces no diff (idempotent). ``foundations.json`` is
NOT read here: countries/visa/airports/airlines/fx were merged by an earlier task.
"""

from __future__ import annotations

import glob
import json
import re
import subprocess
import sys
from pathlib import Path

_APPS_API = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_APPS_API) not in sys.path:
    sys.path.insert(0, str(_APPS_API))

from app.db.base import deterministic_uuid  # noqa: E402

SOURCES_DIR = _REPO_ROOT / "specs" / "gh-237-city-coverage-expansion" / "sources"
DATA_DIR = _APPS_API / "app" / "data"

# Kyoto has no airport of its own; it uses its IATA metropolitan city code.
_HOTEL_CODE_PREFIX_OVERRIDE = {"Kyoto": "UKY"}

# Hotel fields rendered into HOTELS, in the exact order of an existing row.
_HOTEL_FIELDS = [
    "name",
    "address",
    "star_rating",
    "price_per_night",
    "currency",
    "amenities",
    "image_url",
    "rating",
    "review_count",
    "description",
    "property_type",
    "chain",
    "check_in_time",
    "check_out_time",
    "breakfast_included",
    "free_cancellation",
    "languages_spoken",
]
# Place fields, in the exact order of an existing PLACES row.
_PLACE_FIELDS = [
    "name",
    "city",
    "country",
    "category",
    "description",
    "address",
    "rating",
    "review_count",
    "price_level",
    "opening_hours",
    "image_url",
    "tags",
    "is_recommended",
    "latitude",
    "longitude",
]


def pyval(value) -> str:
    """Render a JSON-loaded scalar/list as a Python literal (bools/None fixed)."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(pyval(v) for v in value) + "]"
    raise TypeError(f"unsupported value type for rendering: {type(value)!r}")


def _kv(indent: int, key: str, value) -> str:
    return f"{' ' * indent}{json.dumps(key)}: {pyval(value)},"


def load_city_files() -> list[dict]:
    """Return every city object across the six region files, in a stable order."""
    cities: list[dict] = []
    for path in sorted(glob.glob(str(SOURCES_DIR / "*.json"))):
        name = Path(path).name
        if name in {"foundations.json", "countries.json"}:
            continue
        cities.extend(json.loads(Path(path).read_text(encoding="utf-8")))
    return cities


def load_countries() -> list[dict]:
    return json.loads((SOURCES_DIR / "countries.json").read_text(encoding="utf-8"))


# --- renderers -------------------------------------------------------------


def render_cities(city_objs: list[dict]) -> str:
    out: list[str] = []
    for obj in city_objs:
        c = obj["city"]
        out.append("    {")
        out.append(_kv(8, "name", c["name"]))
        out.append(_kv(8, "country", c["country"]))
        out.append(_kv(8, "airport_codes", c["airport_codes"]))
        out.append(_kv(8, "latitude", c["latitude"]))
        out.append(_kv(8, "longitude", c["longitude"]))
        out.append("    },")
    return "\n".join(out) + "\n"


# Curators wrote brand names; the catalogue names the parent group (see existing
# rows). A name guessed from the hotel's own name, or none, is "Independent".
_CHAIN_GROUPS = {
    "Hilton": "Hilton",
    "Waldorf Astoria": "Hilton",
    "Conrad": "Hilton",
    "Hyatt": "Hyatt",
    "Park Hyatt": "Hyatt",
    "Marriott": "Marriott International",
    "Westin": "Marriott International",
    "Sheraton": "Marriott International",
    "W Hotels": "Marriott International",
    "Starwood": "Marriott International",
    "Ritz-Carlton": "The Ritz-Carlton (Marriott)",
    "Accor": "Accor",
    "Fairmont": "Accor",
    "Sofitel": "Accor",
    "Raffles": "Accor",
    "IHG": "IHG Hotels & Resorts",
    "Crowne Plaza": "IHG Hotels & Resorts",
    "ANA": "IHG Hotels & Resorts",
    "Shangri-La": "Shangri-La Group",
    "Peninsula": "The Peninsula Hotels",
    "Lotte": "Lotte Hotels & Resorts",
    "Wyndham": "Wyndham Hotels & Resorts",
    "Anantara": "Minor Hotels",
    "Tivoli": "Minor Hotels",
    "Four Seasons": "Four Seasons",
    "Mandarin Oriental": "Mandarin Oriental",
    "Choice Hotels": "Choice Hotels International",
    "Pestana": "Pestana Hotel Group",
    "Jumeirah": "Jumeirah",
    "Dorchester Collection": "Dorchester Collection",
    "Okura": "Okura Hotels & Resorts",
    "New Otani": "New Otani",
    "Hankyu": "Hankyu Hanshin Hotels",
    "Monterey": "Hotel Monterey",
    "Altis": "Altis Hotels",
    "Imperial": "Imperial Hotel",
    "JR": "JR Hotel Group",
}
# Curator "chains" that are only the hotel's own name.
_NAME_ONLY_CHAINS = {"Jozankei", "Shogetsu", "Kokusai"}


def chain_group(chain: str | None) -> str:
    if chain is None or chain in _NAME_ONLY_CHAINS:
        return "Independent"
    if chain not in _CHAIN_GROUPS:
        raise ValueError(f"unmapped hotel chain {chain!r}: add it to _CHAIN_GROUPS")
    return _CHAIN_GROUPS[chain]


def render_hotels(city_objs: list[dict]) -> str:
    out: list[str] = []
    seen_codes: set[str] = set()
    seen_ids: set[str] = set()
    for obj in city_objs:
        city_name = obj["city"]["name"]
        prefix = _HOTEL_CODE_PREFIX_OVERRIDE.get(
            city_name, obj["city"]["airport_codes"][0]
        )
        for i, hotel in enumerate(obj["hotels"], start=1):
            code = f"{prefix}{i:03d}"
            if code in seen_codes:
                raise ValueError(f"duplicate hotel code generated: {code}")
            seen_codes.add(code)
            hid = deterministic_uuid("hotel", code)
            if hid in seen_ids:
                raise ValueError(f"duplicate hotel id generated: {hid} ({code})")
            seen_ids.add(hid)
            out.append("    {")
            out.append(_kv(8, "id", hid))
            out.append(_kv(8, "code", code))
            for field in _HOTEL_FIELDS:
                value = hotel.get(field)
                if field == "address":
                    out.append(_kv(8, "city", city_name))
                if field == "chain":
                    value = chain_group(value)
                out.append(_kv(8, field, value))
            out.append("    },")
    return "\n".join(out) + "\n"


def render_places(city_objs: list[dict]) -> str:
    out: list[str] = []
    seen_ids: set[str] = set()
    for obj in city_objs:
        city_name = obj["city"]["name"]
        country = obj["city"]["country"]
        for place in obj["places"]:
            pid = deterministic_uuid("place", city_name, place["name"])
            if pid in seen_ids:
                raise ValueError(
                    f"duplicate place id for ({city_name}, {place['name']})"
                )
            seen_ids.add(pid)
            enriched = dict(place, city=city_name, country=country)
            out.append("    {")
            out.append(_kv(8, "id", pid))
            for field in _PLACE_FIELDS:
                out.append(_kv(8, field, enriched.get(field)))
            out.append("    },")
    return "\n".join(out) + "\n"


def _render_tip_list(indent: int, key: str, tips: list[dict]) -> list[str]:
    lines = [f"{' ' * indent}{json.dumps(key)}: ["]
    for tip in tips:
        lines.append(f"{' ' * (indent + 4)}{{")
        for field in ("category", "title", "content", "is_essential"):
            lines.append(_kv(indent + 8, field, tip[field]))
        lines.append(f"{' ' * (indent + 4)}}},")
    lines.append(f"{' ' * indent}],")
    return lines


def render_country_tips(countries: list[dict]) -> str:
    out: list[str] = []
    for country in countries:
        out.extend(_render_tip_list(4, country["country"], country["tips"]))
    return "\n".join(out) + "\n"


def render_city_tips(city_objs: list[dict]) -> str:
    out: list[str] = []
    for obj in city_objs:
        out.extend(_render_tip_list(4, obj["city"]["name"], obj["city_tips"]))
    return "\n".join(out) + "\n"


def render_country_summaries(countries: list[dict]) -> str:
    out: list[str] = []
    for country in countries:
        out.append(_kv(4, country["country"], country["summary"]))
    return "\n".join(out) + "\n"


# --- splicing --------------------------------------------------------------


def _strip_block(text: str, tag: str) -> str:
    pattern = rf" *# BEGIN gh-237 {re.escape(tag)}\n.*? *# END gh-237 {re.escape(tag)}[^\n]*\n"
    return re.sub(pattern, "", text, flags=re.S)


def splice(text: str, tag: str, anchor: str, body: str) -> str:
    if anchor not in text:
        raise ValueError(f"anchor not found for tag {tag!r}: {anchor!r}")
    begin, end = f"# BEGIN gh-237 {tag}\n", f"# END gh-237 {tag}\n"
    if text.count(begin) > 1 or text.count(begin) != text.count(end):
        raise ValueError(f"unbalanced gh-237 markers for tag {tag!r}")
    text = _strip_block(text, tag)
    if begin in text:
        raise ValueError(f"could not strip the previous {tag!r} block")
    block = f"    {begin}{body}    {end}"
    return text.replace(anchor, block + anchor, 1)


def main() -> int:
    city_objs = load_city_files()
    countries = load_countries()

    edits = {
        "cities.py": [
            (
                "cities",
                "]\n\n# Reject any city whose country is absent",
                render_cities(city_objs),
            ),
        ],
        "hotels.py": [
            ("hotels", "]\n\n# A hotel naming a city absent", render_hotels(city_objs)),
        ],
        "places.py": [
            (
                "places",
                "]\n\n# Reject any place whose country is absent",
                render_places(city_objs),
            ),
        ],
        "tips.py": [
            ("country-tips", "}\n\nCITY_TIPS: dict", render_country_tips(countries)),
            ("city-tips", "}\n\nCOUNTRY_SUMMARIES: dict", render_city_tips(city_objs)),
            (
                "country-summaries",
                "}\n\n# Reject keys absent",
                render_country_summaries(countries),
            ),
        ],
    }

    for filename, specs in edits.items():
        path = DATA_DIR / filename
        text = path.read_text(encoding="utf-8")
        for tag, anchor, body in specs:
            text = splice(text, tag, anchor, body)
        path.write_text(text, encoding="utf-8")

    ruff = _APPS_API.parents[1] / ".venv" / "bin" / "ruff"
    ruff_bin = str(ruff) if ruff.exists() else "ruff"
    subprocess.run([ruff_bin, "format", "app/data"], cwd=str(_APPS_API), check=True)
    print(
        f"imported {len(city_objs)} cities and {len(countries)} countries; "
        "ran ruff format on app/data"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
