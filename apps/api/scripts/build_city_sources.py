#!/usr/bin/env python3
"""Build the region provenance files from candidate files plus curated selections.

A selection (``selections/<city>.json``) only names candidate QIDs and supplies the
indicative values (stars, price, rating, amenities...), a place description with a
verbatim ``evidence`` quote from the candidate's Wikipedia extract, and city tips
with a verbatim ``evidence`` quote from the candidate's Wikivoyage text. Names,
coordinates, images, addresses and QIDs are copied from ``candidates/<city>.json``,
so a curator cannot introduce them.

    python -m scripts.build_city_sources            # all regions
    python -m scripts.build_city_sources --check    # validate selections only

Exits 1 when any selection references an unknown QID, a quote is not found in its
source text, or a number in generated prose does not occur in the source text.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

SPEC = Path(__file__).resolve().parents[3] / "specs" / "gh-237-city-coverage-expansion"

CITIES: dict[str, dict] = {
    "Osaka": {
        "country": "Japan",
        "airports": ["KIX", "ITM"],
        "lat": 34.6938,
        "lon": 135.5021,
        "wiki": "Osaka",
        "voyage": "Osaka",
    },
    "Kyoto": {
        "country": "Japan",
        "airports": ["KIX", "ITM"],
        "lat": 35.0116,
        "lon": 135.7681,
        "wiki": "Kyoto",
        "voyage": "Kyoto",
    },
    "Fukuoka": {
        "country": "Japan",
        "airports": ["FUK"],
        "lat": 33.5901,
        "lon": 130.4017,
        "wiki": "Fukuoka",
        "voyage": "Fukuoka",
    },
    "Sapporo": {
        "country": "Japan",
        "airports": ["CTS"],
        "lat": 43.0619,
        "lon": 141.3544,
        "wiki": "Sapporo",
        "voyage": "Sapporo",
    },
    "Busan": {
        "country": "South Korea",
        "airports": ["PUS"],
        "lat": 35.18,
        "lon": 129.075,
        "wiki": "Busan",
        "voyage": "Busan",
    },
    "Jeju": {
        "country": "South Korea",
        "airports": ["CJU"],
        "lat": 33.5097,
        "lon": 126.5219,
        "wiki": "Jeju_City",
        "voyage": "Jeju_City",
    },
    "Taipei": {
        "country": "Taiwan",
        "airports": ["TPE", "TSA"],
        "lat": 25.0375,
        "lon": 121.5625,
        "wiki": "Taipei",
        "voyage": "Taipei",
    },
    "Shanghai": {
        "country": "China",
        "airports": ["PVG", "SHA"],
        "lat": 31.2325,
        "lon": 121.4692,
        "wiki": "Shanghai",
        "voyage": "Shanghai",
    },
    "Beijing": {
        "country": "China",
        "airports": ["PEK", "PKX"],
        "lat": 39.904,
        "lon": 116.4075,
        "wiki": "Beijing",
        "voyage": "Beijing",
    },
    "Guangzhou": {
        "country": "China",
        "airports": ["CAN"],
        "lat": 23.13,
        "lon": 113.26,
        "wiki": "Guangzhou",
        "voyage": "Guangzhou",
    },
    "Paris": {
        "country": "France",
        "airports": ["CDG", "ORY"],
        "lat": 48.8567,
        "lon": 2.3522,
        "wiki": "Paris",
        "voyage": "Paris",
    },
    "London": {
        "country": "United Kingdom",
        "airports": ["LHR", "LGW"],
        "lat": 51.5072,
        "lon": -0.1275,
        "wiki": "London",
        "voyage": "London",
    },
    "Lisbon": {
        "country": "Portugal",
        "airports": ["LIS"],
        "lat": 38.708,
        "lon": -9.139,
        "wiki": "Lisbon",
        "voyage": "Lisbon",
    },
    "Rome": {
        "country": "Italy",
        "airports": ["FCO"],
        "lat": 41.8931,
        "lon": 12.4828,
        "wiki": "Rome",
        "voyage": "Rome",
    },
    "Sydney": {
        "country": "Australia",
        "airports": ["SYD"],
        "lat": -33.8678,
        "lon": 151.21,
        "wiki": "Sydney",
        "voyage": "Sydney",
    },
    "Melbourne": {
        "country": "Australia",
        "airports": ["MEL"],
        "lat": -37.8142,
        "lon": 144.9631,
        "wiki": "Melbourne",
        "voyage": "Melbourne",
    },
    "Dubai": {
        "country": "United Arab Emirates",
        "airports": ["DXB"],
        "lat": 25.2697,
        "lon": 55.3094,
        "wiki": "Dubai",
        "voyage": "Dubai",
    },
    "Istanbul": {
        "country": "Turkey",
        "airports": ["IST", "SAW"],
        "lat": 41.01,
        "lon": 28.9603,
        "wiki": "Istanbul",
        "voyage": "Istanbul",
    },
    "New York": {
        "country": "United States",
        "airports": ["JFK", "EWR"],
        "lat": 40.7128,
        "lon": -74.0061,
        "wiki": "New_York_City",
        "voyage": "New_York_City",
    },
    "Los Angeles": {
        "country": "United States",
        "airports": ["LAX"],
        "lat": 34.0522,
        "lon": -118.2437,
        "wiki": "Los_Angeles",
        "voyage": "Los_Angeles",
    },
}

REGIONS: dict[str, list[str]] = {
    "japan": ["Osaka", "Kyoto", "Fukuoka", "Sapporo"],
    "korea_taiwan": ["Busan", "Jeju", "Taipei"],
    "china": ["Shanghai", "Beijing", "Guangzhou"],
    "europe": ["Paris", "London", "Lisbon", "Rome"],
    "oceania_me": ["Sydney", "Melbourne", "Dubai", "Istanbul"],
    "usa": ["New York", "Los Angeles"],
}

_HOTEL_VALUE_KEYS = (
    "star_rating",
    "price_per_night",
    "amenities",
    "rating",
    "review_count",
    "property_type",
    "chain",
    "check_in_time",
    "check_out_time",
    "breakfast_included",
    "free_cancellation",
    "languages_spoken",
)
_PLACE_VALUE_KEYS = (
    "category",
    "description",
    "rating",
    "review_count",
    "price_level",
    "opening_hours",
    "tags",
    "is_recommended",
)


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if len(p.strip()) >= 30]


def resolve_evidence(
    ref: str,
    candidates: dict,
    qid: str | None = None,
) -> str | None:
    """Map ``wv:<n>`` or ``wp:<n>`` (numbered in the digest) to its sentence."""
    m = re.fullmatch(r"(wv|wp):(\d+)", ref or "")
    if not m:
        return None
    kind, n = m.group(1), int(m.group(2))
    if kind == "wv":
        pool = sentences(
            "\n".join(v for v in candidates.get("wikivoyage", {}).values() if v)
        )
    else:
        extract = (candidates.get("wikipedia", {}).get(qid) or {}).get("extract") or ""
        pool = sentences(extract)
    return pool[n] if 0 <= n < len(pool) else None


def _numbers(text: str) -> list[str]:
    return [n.rstrip(".,") for n in re.findall(r"\d[\d,.]*", text) if n.rstrip(".,")]


def _hotel_description(
    name: str,
    city: str,
    country: str,
    hotel: dict,
) -> str:
    kind = hotel["property_type"].lower()
    amenities = [a.lower() for a in hotel["amenities"]]
    if len(amenities) > 1:
        offering = ", ".join(amenities[:-1]) + " and " + amenities[-1]
    else:
        offering = amenities[0] if amenities else "a comfortable stay"
    return (
        f"{name} is a {hotel['star_rating']}-star {kind} in {city}, {country}, offering {offering}. "
        f"It holds a {hotel['rating']}/5 guest rating across {hotel['review_count']:,} reviews."
    )


def _wiki_url(title: str | None, qid: str) -> str:
    if title:
        return "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
    return f"https://www.wikidata.org/wiki/{qid}"


def build_city(
    city: str,
    errors: list[str],
) -> dict | None:
    meta = CITIES[city]
    cand_path = SPEC / "candidates" / f"{city}.json"
    sel_path = SPEC / "selections" / f"{city}.json"
    if not sel_path.exists():
        errors.append(f"{city}: no selection file {sel_path.name}")
        return None
    cand = json.loads(cand_path.read_text())
    sel = json.loads(sel_path.read_text())
    by_qid = {
        c["qid"]: c for key in ("hotels", "places", "restaurants") for c in cand[key]
    }
    wiki = cand.get("wikipedia", {})
    voyage = _norm(" ".join(v for v in cand.get("wikivoyage", {}).values() if v))
    voyage_raw = " ".join(v for v in cand.get("wikivoyage", {}).values() if v)

    hotels = []
    for h in sel.get("hotels", []):
        c = by_qid.get(h.get("qid"))
        if c is None or c not in cand["hotels"]:
            errors.append(
                f"{city}: hotel qid {h.get('qid')!r} is not a hotel candidate"
            )
            continue
        missing = [k for k in _HOTEL_VALUE_KEYS if k not in h]
        if missing:
            errors.append(f"{city}: hotel {c['label']}: missing {missing}")
            continue
        image = c.get("image_url") or cand["landmark_image"]
        record = {
            "name": c["label"],
            "address": c.get("address") or city,
            **{k: h[k] for k in _HOTEL_VALUE_KEYS},
            "currency": "USD",
            "image_url": image,
            "latitude": round(c["latitude"], 6),
            "longitude": round(c["longitude"], 6),
            "wikidata": c["qid"],
            "source_url": f"https://www.wikidata.org/wiki/{c['qid']}",
        }
        record["description"] = _hotel_description(c["label"], city, meta["country"], h)
        if not c.get("image_url"):
            record["image_note"] = (
                "no Commons image for this hotel; city landmark image used"
            )
        hotels.append(record)

    places = []
    for p in sel.get("places", []):
        c = by_qid.get(p.get("qid"))
        if c is None or c in cand["hotels"]:
            errors.append(
                f"{city}: place qid {p.get('qid')!r} is not a place/restaurant candidate"
            )
            continue
        missing = [k for k in _PLACE_VALUE_KEYS + ("evidence",) if k not in p]
        if missing:
            errors.append(f"{city}: place {c['label']}: missing {missing}")
            continue
        extract = (wiki.get(c["qid"]) or {}).get("extract") or ""
        if str(p["evidence"]).startswith("wp:"):
            p["evidence"] = (
                resolve_evidence(p["evidence"], cand, c["qid"]) or p["evidence"]
            )
        source_text = (
            extract + " " + " ".join(c.get("instance_of") or []) + " " + c["label"]
        )
        if _norm(p["evidence"]) not in _norm(source_text) or len(p["evidence"]) < 3:
            errors.append(
                f"{city}: place {c['label']}: evidence not found in its extract/instance_of: {p['evidence'][:80]!r}"
            )
        for n in _numbers(p["description"]):
            if n not in source_text:
                errors.append(
                    f"{city}: place {c['label']}: number {n!r} in description not in its source text"
                )
        image = c.get("image_url") or cand["landmark_image"]
        record = {
            "name": c["label"],
            **{k: p[k] for k in _PLACE_VALUE_KEYS},
            "address": c.get("address") or p.get("address") or city,
            "image_url": image,
            "latitude": round(c["latitude"], 6),
            "longitude": round(c["longitude"], 6),
            "wikidata": c["qid"],
            "source_url": _wiki_url(c.get("en_title") if extract else None, c["qid"]),
            "evidence": p["evidence"],
        }
        if not c.get("image_url"):
            record["image_note"] = (
                "no Commons image for this place; city landmark image used"
            )
        places.append(record)

    tips = []
    for t in sel.get("city_tips", []):
        ev = t.get("evidence", "")
        if ev.startswith("wv:"):
            ev = resolve_evidence(ev, cand) or ev
        if len(ev) < 30 or _norm(ev) not in voyage:
            errors.append(
                f"{city}: tip {t.get('title')!r}: evidence not found in Wikivoyage text"
            )
        for n in _numbers(t.get("content", "")):
            if n not in voyage_raw:
                errors.append(
                    f"{city}: tip {t.get('title')!r}: number {n!r} not in Wikivoyage text"
                )
        tips.append(
            {
                "category": t["category"],
                "title": t["title"],
                "content": t["content"],
                "is_essential": t["is_essential"],
                "source_url": "https://en.wikivoyage.org/wiki/" + meta["voyage"],
                "evidence": ev,
            }
        )

    return {
        "city": {
            "name": city,
            "country": meta["country"],
            "airport_codes": meta["airports"],
            "latitude": meta["lat"],
            "longitude": meta["lon"],
            "wikidata": cand["wikidata_qid"],
            "source_url": "https://en.wikipedia.org/wiki/" + meta["wiki"],
        },
        "hotels": hotels,
        "places": places,
        "city_tips": tips,
    }


def _checker_violations(
    region: str,
    built: list[dict],
) -> list[str]:
    from scripts.check_seed_sources import check_path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{region}.json"
        path.write_text(json.dumps(built, ensure_ascii=False))
        return check_path(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="validate selections, write nothing"
    )
    parser.add_argument(
        "--region", choices=sorted(REGIONS), help="build one region only"
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    regions = [args.region] if args.region else list(REGIONS)
    for region in regions:
        built = [b for b in (build_city(c, errors) for c in REGIONS[region]) if b]
        if built:
            errors.extend(_checker_violations(region, built))
        if not args.check and len(built) == len(REGIONS[region]):
            out = SPEC / "sources" / f"{region}.json"
            out.write_text(json.dumps(built, ensure_ascii=False, indent=2) + "\n")
            print(f"wrote {out.relative_to(SPEC.parent.parent)}")
    for e in errors:
        print(e)
    print(f"{len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
