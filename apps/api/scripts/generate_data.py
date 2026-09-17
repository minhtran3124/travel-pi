#!/usr/bin/env python3
"""Generate additional mock hotel records for the Travel Planner Mock API.

A manual developer tool: it prints ready-to-paste Python dict literals (or JSON)
for new hotels in a given city, to paste into ``app/data/hotels.py``. IDs continue
from existing records so they never collide.

Examples::

    python scripts/generate_data.py hotels --city "Da Nang" --count 3
    python scripts/generate_data.py hotels --city "Hoi An" --count 2 --seed 42
    python scripts/generate_data.py hotels --city "Hanoi" --count 1 --json
    python scripts/generate_data.py hotels --city "Hue" --prefix hue --count 2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

# Allow `from app...` imports when the script is run directly by path.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Known city -> ID prefix, matching the convention in app/data/hotels.py.
CITY_PREFIXES: dict[str, str] = {
    # Vietnam
    "Da Nang": "dn",
    "Hanoi": "hn",
    "Ho Chi Minh City": "hcm",
    "Hoi An": "ha",
    "Phu Quoc": "pq",
    "Nha Trang": "nt",
    # Thailand
    "Bangkok": "bkk",
    "Phuket": "pkt",
    "Chiang Mai": "cm",
    # Singapore
    "Singapore": "sg",
    # Malaysia
    "Kuala Lumpur": "kl",
    # Indonesia
    "Bali": "bali",
    "Jakarta": "jkt",
    # Cambodia
    "Siem Reap": "sr",
    # Laos
    "Luang Prabang": "lp",
    # Myanmar
    "Yangon": "yg",
    # Philippines
    "Manila": "mnl",
    "Cebu": "cb",
}

AMENITY_POOL = [
    "Pool",
    "Spa",
    "Beach Access",
    "Restaurant",
    "Bar",
    "Gym",
    "Free WiFi",
]

# Enrichment derives the richer descriptive fields as a pure function of a
# record, so the seed file and freshly generated records stay consistent.
# This is the single source of truth: app/data/hotels.py was populated by it.

# Front-desk languages by country (English is assumed everywhere here).
COUNTRY_LANGUAGES: dict[str, list[str]] = {
    "Vietnam": ["English", "Vietnamese"],
    "Thailand": ["English", "Thai"],
    "Singapore": ["English", "Mandarin", "Malay"],
    "Malaysia": ["English", "Malay"],
    "Indonesia": ["English", "Indonesian"],
    "Cambodia": ["English", "Khmer"],
    "Laos": ["English", "Lao"],
    "Myanmar": ["English", "Burmese"],
    "Philippines": ["English", "Filipino"],
    "Brunei": ["English", "Malay"],
    "Timor-Leste": ["English", "Portuguese", "Tetum"],
    "Hong Kong": ["English", "Cantonese", "Mandarin"],
    "South Korea": ["English", "Korean"],
    "Japan": ["English", "Japanese"],
}

# Brand keyword -> operating group, checked most-specific first.
HOTEL_CHAINS: list[tuple[tuple[str, ...], str]] = [
    (("Ritz-Carlton",), "The Ritz-Carlton (Marriott)"),
    (
        (
            "JW Marriott",
            "Marriott",
            "Renaissance",
            "Sheraton",
            "Westin",
            "Le Meridien",
            "Le Méridien",
            "St. Regis",
            "Tribute Portfolio",
        ),
        "Marriott International",
    ),
    (("Park Hyatt", "Grand Hyatt", "Hyatt Regency", "Hyatt"), "Hyatt"),
    (("DoubleTree", "Conrad", "Waldorf", "Hilton"), "Hilton"),
    (("InterContinental", "Crowne Plaza", "Holiday Inn"), "IHG Hotels & Resorts"),
    (
        ("Sofitel", "Novotel", "Pullman", "Mercure", "Raffles", "Fairmont"),
        "Accor",
    ),
    (("Four Seasons",), "Four Seasons"),
    (("Shangri-La",), "Shangri-La Group"),
    (("Mandarin Oriental",), "Mandarin Oriental"),
    (("Peninsula",), "The Peninsula Hotels"),
    (("Banyan Tree",), "Banyan Tree Group"),
    (("Anantara", "Avani", "AVANI"), "Minor Hotels"),
    (("Six Senses",), "Six Senses"),
    (("Rosewood",), "Rosewood Hotels & Resorts"),
    (("Amanpuri", "Amantaka", "Aman"), "Aman"),
    (("COMO",), "COMO Hotels & Resorts"),
    (("Bulgari",), "Bulgari Hotels & Resorts"),
    (("AYANA",), "AYANA"),
    (("Mulia",), "The Mulia"),
    (("Vinpearl", "Melia Vinpearl"), "Vinpearl"),
    (("Centara",), "Centara Hotels & Resorts"),
    (("Dusit",), "Dusit International"),
    (("Radisson",), "Radisson Hotel Group"),
    (("Lotte",), "Lotte Hotels & Resorts"),
    (("Shilla",), "The Shilla"),
    (("Melia", "Meliá"), "Meliá Hotels International"),
    (("Swiss-Bel",), "Swiss-Belhotel International"),
    (("Aston",), "Archipelago International"),
    (("Muong Thanh",), "Muong Thanh Hospitality"),
    (("Pan Pacific",), "Pan Pacific Hotels Group"),
    (("Chatrium",), "Chatrium Hotels & Residences"),
    (("Sokha",), "Sokha Hotels & Resorts"),
    (("Marco Polo",), "Wharf Hotels"),
    (("Seda",), "Ayala Land Hospitality"),
    (("Henann",), "Henann Group of Resorts"),
    (("Furama",), "Furama Hotels International"),
]


def _hotel_chain(name: str) -> str:
    """Resolve a hotel name to its operating group, or 'Independent'."""
    for keywords, brand in HOTEL_CHAINS:
        if any(kw in name for kw in keywords):
            return brand
    return "Independent"


def _property_type(name: str, amenities: list[str]) -> str:
    """Classify a property from name keywords and amenities."""
    if "Boutique" in name:
        return "Boutique Hotel"
    if "Villa" in name or "Villas" in name:
        return "Villa Resort"
    if "Resort" in name or "Beach Access" in amenities:
        return "Resort"
    return "Hotel"


def _amenity_phrase(amenities: list[str]) -> str:
    """Join amenities into prose: 'pool, spa and a restaurant'."""
    items = [a.lower() for a in amenities]
    if not items:
        return "comfortable rooms"
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _describe_hotel(record: dict, country: str) -> str:
    """Compose a one-paragraph blurb, varied deterministically by ID."""
    ptype = _property_type(record["name"], record["amenities"]).lower()
    amen = _amenity_phrase(record["amenities"])
    name, city = record["name"], record["city"]
    stars, rating = record["star_rating"], record["rating"]
    reviews = f"{record['review_count']:,}"
    templates = [
        f"{name} is a {stars}-star {ptype} in {city}, {country}, offering {amen}. "
        f"It holds a {rating}/5 guest rating across {reviews} reviews.",
        f"Set in {city}, {country}, {name} is a {stars}-star {ptype} known for {amen}. "
        f"Travellers rate it {rating}/5 from {reviews} reviews.",
        f"{name} brings {stars}-star comfort to {city}, {country}, with {amen}. "
        f"It earns {rating}/5 over {reviews} guest reviews.",
    ]
    pick = int(hashlib.md5(record["id"].encode()).hexdigest(), 16) % len(templates)
    return templates[pick]


def _det_bool(seed: str, threshold: int) -> bool:
    """Deterministic pseudo-random bool — True with ~``threshold``% odds."""
    return int(hashlib.md5(seed.encode()).hexdigest(), 16) % 100 < threshold


def enrich_hotel(record: dict, country: str) -> dict:
    """Return the richer descriptive fields for a hotel record.

    Pure function of ``record`` + ``country``; safe to call repeatedly.
    """
    stars = record["star_rating"]
    return {
        "description": _describe_hotel(record, country),
        "property_type": _property_type(record["name"], record["amenities"]),
        "chain": _hotel_chain(record["name"]),
        "check_in_time": "15:00" if stars >= 5 else "14:00",
        "check_out_time": "11:00" if stars <= 3 else "12:00",
        "breakfast_included": _det_bool(record["id"] + "breakfast", 70),
        "free_cancellation": _det_bool(record["id"] + "cancel", 75),
        "languages_spoken": COUNTRY_LANGUAGES.get(country, ["English"]),
    }


# Building blocks for plausible-sounding hotel names.
NAME_BRANDS = [
    "Hilton",
    "Marriott",
    "Hyatt",
    "Pullman",
    "Sheraton",
    "Wyndham",
    "Movenpick",
    "Vinpearl",
    "Fusion",
    "Melia",
    "Radisson",
    "Mercure",
]
NAME_STYLES = [
    "Resort",
    "Hotel",
    "Beach Resort",
    "Suites",
    "Boutique Hotel",
    "Riverside Hotel",
    "Grand Hotel",
]
STREET_NAMES = [
    "Tran Phu Street",
    "Le Loi Boulevard",
    "Bach Dang Street",
    "Vo Nguyen Giap Street",
    "Nguyen Hue Boulevard",
    "Hai Ba Trung Street",
    "Pham Van Dong Street",
    "Ngo Quyen Street",
]


def _resolve_prefix(city: str, explicit: str | None) -> str:
    """Pick an ID prefix: explicit flag > known city > derived from name."""
    if explicit:
        return explicit.lower()
    if city in CITY_PREFIXES:
        return CITY_PREFIXES[city]
    words = city.split()
    if len(words) >= 2:
        return "".join(word[0] for word in words).lower()
    return city[:3].lower()


def _existing_index(city: str) -> int:
    """Highest hotel index already used for ``city`` (0 if none / unreadable).

    Reading the seed file is best-effort; a failed import falls back to 0.
    """
    try:
        from app.data.hotels import HOTELS
    except Exception:  # pragma: no cover - best-effort convenience only
        return 0
    # Each ID looks like "h_dn_05"; rsplit on the last "_" gives the number.
    indexes = [
        int(hotel["id"].rsplit("_", 1)[-1])
        for hotel in HOTELS
        if hotel.get("city") == city
    ]
    return max(indexes, default=0)


def _make_hotel(
    city: str,
    prefix: str,
    index: int,
    rng: random.Random,
    min_price: int,
    max_price: int,
) -> dict:
    """Build a single hotel record following the spec's field rules."""
    hotel_id = f"h_{prefix}_{index:02d}"
    brand = rng.choice(NAME_BRANDS)
    style = rng.choice(NAME_STYLES)
    record = {
        "id": hotel_id,
        "name": f"{brand} {city} {style}",
        "city": city,
        "address": f"{rng.randint(1, 300)} {rng.choice(STREET_NAMES)}",
        "star_rating": rng.randint(3, 5),
        "price_per_night": rng.randint(min_price, max_price),
        "currency": "USD",
        "amenities": rng.sample(AMENITY_POOL, rng.randint(3, 5)),
        "image_url": f"https://picsum.photos/seed/{hotel_id}/600/400",
        "rating": round(rng.uniform(4.0, 4.9), 1),
        "review_count": rng.randint(500, 5000),
    }
    # Derive country from cities.py (the source hotels.py uses) so generated
    # records' languages match the seed.
    try:
        from app.data.cities import CITIES

        country = next((c["country"] for c in CITIES if c["name"] == city), "")
    except Exception:  # pragma: no cover - best-effort convenience only
        country = ""
    record.update(enrich_hotel(record, country))
    return record


def _render_python(hotel: dict) -> str:
    """Render a hotel dict as an indented Python literal (4-space indent)."""
    lines = ["    {"]
    for key, value in hotel.items():
        lines.append(f"        {key!r}: {value!r},")
    lines.append("    },")
    return "\n".join(lines)


def _generate_hotels(args: argparse.Namespace) -> int:
    if args.min_price > args.max_price:
        print("error: --min-price must be <= --max-price", file=sys.stderr)
        return 1

    prefix = _resolve_prefix(args.city, args.prefix)
    start = (
        args.start_index
        if args.start_index is not None
        else _existing_index(args.city) + 1
    )
    rng = random.Random(args.seed)

    hotels = [
        _make_hotel(
            args.city, prefix, start + offset, rng, args.min_price, args.max_price
        )
        for offset in range(args.count)
    ]

    if args.json:
        print(json.dumps(hotels, indent=2))
    else:
        print(
            f"# --- {args.count} new hotel(s) for {args.city} "
            f"(prefix '{prefix}', from index {start:02d}) ---"
        )
        for hotel in hotels:
            print(_render_python(hotel))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate extra mock data for the Travel Planner Mock API.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    hotels = subparsers.add_parser("hotels", help="Generate hotel records.")
    hotels.add_argument("--city", required=True, help="City name, e.g. 'Da Nang'.")
    hotels.add_argument("--count", type=int, default=1, help="How many to make.")
    hotels.add_argument("--prefix", help="ID prefix override (for new cities).")
    hotels.add_argument(
        "--start-index",
        type=int,
        default=None,
        help="First ID index. Defaults to continuing from existing data.",
    )
    hotels.add_argument("--min-price", type=int, default=75, help="Min USD/night.")
    hotels.add_argument("--max-price", type=int, default=500, help="Max USD/night.")
    hotels.add_argument("--seed", type=int, default=None, help="RNG seed.")
    hotels.add_argument(
        "--json", action="store_true", help="Emit JSON instead of Python literals."
    )
    hotels.set_defaults(func=_generate_hotels)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
