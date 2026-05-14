#!/usr/bin/env python3
"""Generate additional mock hotel records for the Travel Planner Mock API.

This is a *manual* developer tool. It prints ready-to-paste Python dict
literals (or JSON) for new hotels in a given city. Review the output, then
paste the dicts into the matching city block in ``app/data/hotels.py``.

By default the ID index continues from the hotels already in that city, so
generated records never collide with existing ones.

Examples
--------
    # 3 new Da Nang hotels, IDs continue from existing data
    python scripts/generate_data.py hotels --city "Da Nang" --count 3

    # Reproducible output with a fixed seed
    python scripts/generate_data.py hotels --city "Hoi An" --count 2 --seed 42

    # Emit JSON instead of Python literals
    python scripts/generate_data.py hotels --city "Hanoi" --count 1 --json

    # A brand-new city (provide an ID prefix explicitly)
    python scripts/generate_data.py hotels --city "Hue" --prefix hue --count 2
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# Allow `from app...` imports when the script is run directly.
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

# Amenity pool from the spec (§6.3).
AMENITY_POOL = [
    "Pool",
    "Spa",
    "Beach Access",
    "Restaurant",
    "Bar",
    "Gym",
    "Free WiFi",
]

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

    Lets generated IDs continue from existing data instead of colliding with
    it. Reading the seed file is a convenience only — if the import fails
    (e.g. run from an odd working directory) we just fall back to 0.
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
    return {
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
