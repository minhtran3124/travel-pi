#!/usr/bin/env python3
"""Fetch real hotel/place candidates for a city from Wikidata, Commons, Wikipedia and Wikivoyage.

Writes ``candidates/<city>.json`` (default ``specs/gh-237-city-coverage-expansion/
candidates/``) with the raw material a curation pass selects from: it never invents a
record, name, coordinate or image -- everything traces back to a Wikidata QID.

Run as a module from ``apps/api/``::

    python -m scripts.fetch_city_candidates Osaka Q35765
    python -m scripts.fetch_city_candidates Osaka Q35765 --out ../../specs/.../candidates
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

import certifi
import httpx

USER_AGENT = "travel-pi-seed-check/1.0 (https://github.com/minhtran3124/travel-pi)"
WDQS_URL = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"

_HOTEL_CLASSES = ("Q27686", "Q1524080", "Q1497375")  # hotel, hostel, capsule hotel
_RESTAURANT_CLASSES = ("Q11707", "Q30022")  # restaurant, cafe
_EXCLUDED_PLACE_CLASSES = (
    "Q5",  # human
    "Q4830453",  # business
    "Q783794",  # company
    "Q56061",  # administrative territorial entity
    "Q55488",  # railway station
    "Q928830",  # metro station
)
# Wikidata's class hierarchy has known bad edges (e.g. "amusement park" is
# mis-modelled as a direct P279 subclass of "capsule hotel"), so P279* on
# accommodation classes pulls in theme parks. Excluded explicitly rather than
# bounding subclass depth, which does not clear this specific edge.
# Direct instance-of only, deliberately no subclass-of (P279*) expansion: Wikidata's
# class hierarchy has known bad edges here (e.g. "amusement park" is mis-modelled as a
# direct P279 subclass of "capsule hotel"), which pulled theme parks and office towers
# into hotel/restaurant candidates. These classes are kept as defense in depth.
_EXCLUDED_ACCOMMODATION_CLASSES = (
    "Q2416723",  # theme park
    "Q194195",  # amusement park
    "Q570116",  # tourist attraction
)

_WIKIVOYAGE_SECTIONS = ("Get around", "Stay safe", "Eat", "Sleep")

_SPARQL_TIMEOUT = 60.0
_HTTP_TIMEOUT = 30.0
_SPARQL_SLEEP_S = 1.0
_MAX_TRIES = 3

_last_sparql_call: float = 0.0


def _client_verify() -> str:
    return certifi.where()


def _throttle_sparql() -> None:
    """Sleep so consecutive SPARQL calls stay >= _SPARQL_SLEEP_S apart."""
    global _last_sparql_call
    elapsed = time.monotonic() - _last_sparql_call
    if elapsed < _SPARQL_SLEEP_S:
        time.sleep(_SPARQL_SLEEP_S - elapsed)
    _last_sparql_call = time.monotonic()


def _sparql(query: str) -> list[dict[str, Any]]:
    """Run one SPARQL query against WDQS, retrying 429/5xx with backoff."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    }
    last_exc: Exception | None = None
    for attempt in range(_MAX_TRIES):
        _throttle_sparql()
        try:
            resp = httpx.get(
                WDQS_URL,
                params={"query": query, "format": "json"},
                headers=headers,
                timeout=_SPARQL_TIMEOUT,
                verify=_client_verify(),
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(2.0 * (attempt + 1))
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            wait_s = float(retry_after) if retry_after else 2.0 * (attempt + 1)
            time.sleep(wait_s)
            last_exc = RuntimeError(f"WDQS returned {resp.status_code}")
            continue
        resp.raise_for_status()
        return resp.json()["results"]["bindings"]
    raise RuntimeError(f"SPARQL query failed after {_MAX_TRIES} tries") from last_exc


def _val(binding: dict[str, Any], key: str) -> str | None:
    entry = binding.get(key)
    return entry.get("value") if entry else None


def _qid_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1]


def _parse_point(wkt: str | None) -> tuple[float, float] | None:
    if not wkt:
        return None
    match = re.match(r"Point\(([-\d.]+)\s+([-\d.]+)\)", wkt)
    if not match:
        return None
    lon, lat = float(match.group(1)), float(match.group(2))
    return lat, lon


def _filename_from_p18(image_uri: str | None) -> str | None:
    if not image_uri:
        return None
    marker = "Special:FilePath/"
    idx = image_uri.find(marker)
    if idx == -1:
        return None
    return urllib.parse.unquote(image_uri[idx + len(marker) :])


def _class_values(classes: tuple[str, ...]) -> str:
    return " ".join(f"wd:{c}" for c in classes)


def _hotel_query(qid: str, limit: int) -> str:
    exclusions = "\n".join(
        f"      FILTER NOT EXISTS {{ ?item wdt:P31/wdt:P279* wd:{c} . }}"
        for c in _EXCLUDED_ACCOMMODATION_CLASSES
    )
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?address ?districtLabel ?sitelinks ?enTitle
    WHERE {{
      VALUES ?class {{ {_class_values(_HOTEL_CLASSES)} }}
      ?item wdt:P31 ?class .
      ?item wdt:P131* wd:{qid} .
      ?item wdt:P625 ?coord .
{exclusions}
      OPTIONAL {{ ?item wdt:P18 ?image . }}
      OPTIONAL {{ ?item wdt:P6375 ?address . }}
      OPTIONAL {{ ?item wdt:P131 ?district . }}
      ?item wikibase:sitelinks ?sitelinks .
      OPTIONAL {{
        ?enArticle schema:about ?item ;
                   schema:isPartOf <https://en.wikipedia.org/> ;
                   schema:name ?enTitle .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY DESC(?sitelinks)
    LIMIT {limit}
    """


def _restaurant_query(qid: str, limit: int) -> str:
    exclusions = "\n".join(
        f"      FILTER NOT EXISTS {{ ?item wdt:P31/wdt:P279* wd:{c} . }}"
        for c in _EXCLUDED_ACCOMMODATION_CLASSES
    )
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?address ?sitelinks ?enTitle
    WHERE {{
      VALUES ?class {{ {_class_values(_RESTAURANT_CLASSES)} }}
      ?item wdt:P31 ?class .
      ?item wdt:P131* wd:{qid} .
      ?item wdt:P625 ?coord .
{exclusions}
      OPTIONAL {{ ?item wdt:P18 ?image . }}
      OPTIONAL {{ ?item wdt:P6375 ?address . }}
      ?item wikibase:sitelinks ?sitelinks .
      OPTIONAL {{
        ?enArticle schema:about ?item ;
                   schema:isPartOf <https://en.wikipedia.org/> ;
                   schema:name ?enTitle .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY DESC(?sitelinks)
    LIMIT {limit}
    """


def _place_query(qid: str, limit: int) -> str:
    exclusions = "\n".join(
        f"      FILTER NOT EXISTS {{ ?item wdt:P31/wdt:P279?/wdt:P279? wd:{c} . }}"
        for c in _EXCLUDED_PLACE_CLASSES
    )
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?class ?classLabel ?sitelinks ?enTitle
    WHERE {{
      ?item wdt:P131* wd:{qid} .
      ?item wdt:P625 ?coord .
      ?item wdt:P18 ?image .
      ?item wdt:P31 ?class .
{exclusions}
      ?item wikibase:sitelinks ?sitelinks .
      OPTIONAL {{
        ?enArticle schema:about ?item ;
                   schema:isPartOf <https://en.wikipedia.org/> ;
                   schema:name ?enTitle .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY DESC(?sitelinks)
    LIMIT {limit}
    """


def _merge_place_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The place query yields one row per (item, instance-of class); merge by QID."""
    by_qid: dict[str, dict[str, Any]] = {}
    for row in rows:
        uri = _val(row, "item")
        qid = _qid_from_uri(uri)
        if not qid:
            continue
        entry = by_qid.setdefault(
            qid,
            {
                "qid": qid,
                "label": _val(row, "itemLabel"),
                "coord": _val(row, "coord"),
                "image": _val(row, "image"),
                "sitelinks": _val(row, "sitelinks"),
                "en_title": _val(row, "enTitle"),
                "instance_of": [],
            },
        )
        class_label = _val(row, "classLabel")
        if class_label and class_label not in entry["instance_of"]:
            entry["instance_of"].append(class_label)
    ordered = sorted(
        by_qid.values(), key=lambda e: float(e["sitelinks"] or 0), reverse=True
    )
    return ordered


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _resolve_commons_images(filenames: list[str]) -> dict[str, str]:
    """Resolve Commons file names to a real upload.wikimedia.org URL (thumb, 1280w)."""
    resolved: dict[str, str] = {}
    unique = sorted({f for f in filenames if f})
    headers = {"User-Agent": USER_AGENT}
    for batch in _chunks(unique, 50):
        titles = "|".join(f"File:{name}" for name in batch)
        try:
            resp = httpx.get(
                COMMONS_API,
                params={
                    "action": "query",
                    "titles": titles,
                    "prop": "imageinfo",
                    "iiprop": "url",
                    "iiurlwidth": 1280,
                    "format": "json",
                },
                headers=headers,
                timeout=_HTTP_TIMEOUT,
                verify=_client_verify(),
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            continue
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")
            infos = page.get("imageinfo") or []
            if not infos or not title.startswith("File:"):
                continue
            info = infos[0]
            # Prefer the true upload.wikimedia.org original: Commons' thumburl now
            # resolves through a thumb.wikimedia.org CDN host, which the seed-source
            # checker rejects (it requires an upload.wikimedia.org image_url).
            thumburl = info.get("thumburl")
            fullurl = info.get("url")
            if fullurl and "upload.wikimedia.org" in fullurl:
                url = fullurl
            elif thumburl and "upload.wikimedia.org" in thumburl:
                url = thumburl
            else:
                url = fullurl or thumburl
            if url:
                resolved[title[len("File:") :]] = url
    return resolved


def _fetch_wikipedia_summary(title: str) -> dict[str, str] | None:
    headers = {"User-Agent": USER_AGENT}
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    try:
        resp = httpx.get(
            WIKIPEDIA_SUMMARY_URL.format(title=encoded),
            headers=headers,
            timeout=_HTTP_TIMEOUT,
            verify=_client_verify(),
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    extract = data.get("extract")
    if not extract:
        return None
    return {"title": data.get("title", title), "extract": extract}


def _wikitext_to_plain(text: str) -> str:
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)  # one more pass for shallow nesting
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^\*+\s*", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_sections(wikitext: str, names: tuple[str, ...]) -> dict[str, str]:
    heading_re = re.compile(r"^==+\s*([^=]+?)\s*==+\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(wikitext))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        if heading not in names:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(wikitext)
        sections[heading] = _wikitext_to_plain(wikitext[start:end])
    return sections


def _fetch_wikivoyage_sections(city: str) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = httpx.get(
            WIKIVOYAGE_API,
            params={
                "action": "parse",
                "page": city,
                "prop": "wikitext",
                "format": "json",
            },
            headers=headers,
            timeout=_HTTP_TIMEOUT,
            verify=_client_verify(),
        )
    except httpx.HTTPError:
        return {}
    if resp.status_code != 200:
        return {}
    data = resp.json()
    wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
    if not wikitext:
        return {}
    return _extract_sections(wikitext, _WIKIVOYAGE_SECTIONS)


def _build_hotel_like_entries(
    rows: list[dict[str, Any]],
    image_map: dict[str, str],
) -> list[dict[str, Any]]:
    """One entry per distinct QID. A row repeats per matched class (e.g. an item
    reachable from both ``hotel`` and ``hostel`` via subclass-of), so dedupe here."""
    by_qid: dict[str, dict[str, Any]] = {}
    for row in rows:
        qid = _qid_from_uri(_val(row, "item"))
        if not qid or qid in by_qid:
            continue
        point = _parse_point(_val(row, "coord"))
        filename = _filename_from_p18(_val(row, "image"))
        image_url = image_map.get(filename) if filename else None
        by_qid[qid] = {
            "qid": qid,
            "label": _val(row, "itemLabel"),
            "latitude": point[0] if point else None,
            "longitude": point[1] if point else None,
            "image_url": image_url,
            "address": _val(row, "address") or _val(row, "districtLabel"),
            "sitelinks": int(float(_val(row, "sitelinks") or 0)),
            "en_title": _val(row, "enTitle"),
        }
    return sorted(by_qid.values(), key=lambda e: e["sitelinks"], reverse=True)


def _build_place_entries(
    rows: list[dict[str, Any]],
    image_map: dict[str, str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for row in _merge_place_rows(rows):
        point = _parse_point(row["coord"])
        filename = _filename_from_p18(row["image"])
        image_url = image_map.get(filename) if filename else None
        entries.append(
            {
                "qid": row["qid"],
                "label": row["label"],
                "latitude": point[0] if point else None,
                "longitude": point[1] if point else None,
                "image_url": image_url,
                "instance_of": row["instance_of"],
                "sitelinks": int(float(row["sitelinks"] or 0)),
                "en_title": row["en_title"],
            }
        )
    return entries


def fetch_city_candidates(
    city: str,
    qid: str,
    hotel_limit: int = 40,
    place_limit: int = 60,
    restaurant_limit: int = 30,
) -> dict[str, Any]:
    """Fetch and assemble one city's candidate file. Returns the JSON-ready dict."""
    hotel_rows = _sparql(_hotel_query(qid, hotel_limit))
    place_rows = _sparql(_place_query(qid, place_limit))
    restaurant_rows = _sparql(_restaurant_query(qid, restaurant_limit))

    all_p18_uris = [_val(r, "image") for r in hotel_rows + place_rows + restaurant_rows]
    filenames = [f for f in (_filename_from_p18(u) for u in all_p18_uris) if f]
    image_map = _resolve_commons_images(filenames)

    hotels = _build_hotel_like_entries(hotel_rows, image_map)
    places = _build_place_entries(place_rows, image_map)
    restaurants = _build_hotel_like_entries(restaurant_rows, image_map)

    wikipedia: dict[str, dict[str, str]] = {}
    for entry in hotels + places + restaurants:
        title = entry.get("en_title") or entry.get("label")
        if not title or entry["qid"] in wikipedia:
            continue
        summary = _fetch_wikipedia_summary(title)
        if summary:
            wikipedia[entry["qid"]] = summary

    wikivoyage = _fetch_wikivoyage_sections(city)

    return {
        "city": city,
        "wikidata_qid": qid,
        "hotels": hotels,
        "places": places,
        "restaurants": restaurants,
        "wikipedia": wikipedia,
        "wikivoyage": wikivoyage,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city", help="City name, e.g. Osaka")
    parser.add_argument("qid", help="The city's Wikidata QID, e.g. Q35765")
    parser.add_argument(
        "--out",
        default="../../specs/gh-237-city-coverage-expansion/candidates",
        help="Output directory for <city>.json (default: the plan's candidates dir)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.city}.json"

    data = fetch_city_candidates(args.city, args.qid)
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(
        f"{args.city}: {len(data['hotels'])} hotels, {len(data['places'])} places, "
        f"{len(data['restaurants'])} restaurants -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
