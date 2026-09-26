#!/usr/bin/env python3
"""Fetch real hotel/place candidates for a city from Wikidata, Commons, Wikipedia and Wikivoyage.

Writes ``candidates/<city>.json`` (default ``specs/gh-237-city-coverage-expansion/
candidates/``) with the raw material a curation pass selects from: it never invents a
record, name, coordinate or image -- everything traces back to a Wikidata QID.

Run as a module from ``apps/api``::

    python -m scripts.fetch_city_candidates Osaka Q35765
    python -m scripts.fetch_city_candidates Osaka Q35765 --out ../../specs/.../candidates
    python -m scripts.fetch_city_candidates "Los Angeles" Q65 --max-km 25
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import certifi
import httpx

# Make the `app` package importable when run by path, not only as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.geo import haversine_km

USER_AGENT = "travel-pi-seed-check/1.0 (https://github.com/minhtran3124/travel-pi)"
WDQS_URL = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"

# Exact instance-of only (P31, no P279* subclass expansion): Wikidata's accommodation
# class graph has known bad edges (e.g. "amusement park" is mis-modelled as a direct
# P279 subclass of the old "capsule hotel" QID this fetcher used to point at), so
# subclass expansion pulled in theme parks and office towers as "hotels". Every QID
# below was confirmed live against the Wikidata API before use.
_ACCOMMODATION_CLASSES = (
    "Q27686",  # hotel
    "Q654772",  # hostel
    "Q837834",  # capsule hotel
    "Q562930",  # ryokan
    "Q1761296",  # minshuku
    "Q2880255",  # resort hotel
    "Q259618",  # boutique hotel
    "Q2460422",  # guest house
)
# "Business hotel" has no dedicated Wikidata class distinct from plain "hotel" (Q27686)
# as of this fetch -- confirmed by a live wbsearchentities lookup, not guessed. Hotels
# that are actually business hotels are still reachable via Q27686.
_EXCLUDED_ACCOMMODATION_CLASSES = ("Q1033548",)  # love hotel

# Restaurants and cafes, extended with food markets/market halls (Jagalchi, Nijo,
# Dongmun-style markets), bakeries, izakaya and pubs -- Wikidata coverage for small
# East Asian eateries is sparse, but market halls and drinking-and-food venues are
# well modelled and are a legitimate "eat here" candidate. Every QID confirmed live
# against the Wikidata API (label + a real example item's P31) before use.
_RESTAURANT_CLASSES = (
    "Q11707",  # restaurant
    "Q30022",  # cafe
    "Q1193068",  # izakaya
    "Q212198",  # pub
    "Q274393",  # bakery
    "Q37654",  # market (verified live: Jagalchi Market, Busan)
    "Q1188480",  # fish market (verified live: Nijo fish market, Sapporo)
    "Q2080521",  # market hall
    "Q28142754",  # food market
    "Q330284",  # marketplace
    "Q139784071",  # municipal market
)

# Exact instance-of exclusions for places. Every QID confirmed live. A live SPARQL
# ASK/VALUES probe against WDQS showed that P279* subclass expansion (e.g. resolving
# "occurrence" or "railway station" transitively) reliably times out on this endpoint
# even when bounded to a handful of candidate classes, so -- as with the accommodation
# classes -- exclusions here are exact P31 matches, extended with the specific
# subtypes actually seen on live data rather than a subclass walk.
_EXCLUDED_PLACE_CLASSES = (
    "Q5",  # human
    "Q4830453",  # business
    "Q783794",  # company
    "Q56061",  # administrative territorial entity
    "Q137773",  # ward of Japan (an administrative-area subtype, seen live: Chuo-ku)
    "Q6256",  # country (the radius fallback can otherwise surface the country item
    # itself when it happens to carry a P625 within range, e.g. France near Paris)
    "Q34770",  # language (verified live: "French", Q150, carries its own P625 within
    # the Paris radius search -- a genuine Wikidata data quirk, not a place)
    "Q55488",  # railway station
    "Q928830",  # metro station
    "Q124642584",  # group of railway stations
    "Q11670533",  # elevated station
    "Q1147171",  # interchange station
    "Q7886778",  # union station
    "Q132555858",  # railway station in a highway median
    "Q124416148",  # underground metro station
    "Q5503",  # rapid transit (a transit system/network, not a single place)
    "Q15265344",  # broadcaster
    "Q1616075",  # television station
    "Q3918",  # university
    "Q3914",  # school
    "Q2385804",  # educational institution
    "Q3947",  # house (private residence)
    "Q1307276",  # single-family detached home
    # Occurrences/events: verified live as the actual P31 values seen on Osaka's own
    # bad candidates (a building fire, a mass shooting, a World Expo) rather than
    # walking "occurrence" (Q1190554) via P279*, which timed out on WDQS.
    "Q1190554",  # occurrence
    "Q1656682",  # planned event (label verified live; "event" is only its alias)
    "Q3839081",  # disaster
    "Q7625093",  # structure fire
    "Q168983",  # conflagration
    "Q750215",  # mass murder
    "Q5853505",  # World Expo
    "Q198",  # war
    "Q273120",  # protest
)
# A former/destroyed thing: P5816 (state of use) is one of these. P576 (dissolved /
# demolished date) was tried first per the brief but rejected after live data showed
# it is too blunt: Osaka Castle's own item (Q321242) carries a P576 for the original
# 1615/1868 destructions even though the standing 1931/1997 reconstruction is very
# much an operating landmark with no P5816 marking it destroyed. P5816 is the
# purpose-built "current state of use" property and does not have this false-positive.
_DESTROYED_STATE_OF_USE_CLASSES = (
    "Q56556915",  # demolished or destroyed
    "Q19860854",  # destroyed building or structure
)

_WIKIVOYAGE_SECTIONS = ("Get around", "Stay safe", "Eat", "Sleep")
_WIKIVOYAGE_SECTION_CHAR_CAP = 6000

_DEFAULT_MAX_KM = 15.0

# Below this many P131-chained candidates, also run a --max-km radius search: a
# hotel/restaurant can sit on a district or borough that never P131-chains up to the
# city QID (e.g. Sydney hotels tagged only to the City of Sydney LGA).
_MIN_HOTELS_BEFORE_RADIUS_FALLBACK = 10
_MIN_RESTAURANTS_BEFORE_RADIUS_FALLBACK = 4

_SPARQL_TIMEOUT = 60.0
_HTTP_TIMEOUT = 30.0
_REQUEST_SLEEP_S = 1.0
_MAX_TRIES = 3

_last_request_at: float = 0.0


def _client_verify() -> str:
    return certifi.where()


def _throttle() -> None:
    """Sleep so consecutive outbound API calls stay >= _REQUEST_SLEEP_S apart.

    Applied to every SPARQL, Commons, Wikipedia and Wikivoyage call, not only SPARQL:
    all four are third-party APIs this fetcher must be polite to."""
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < _REQUEST_SLEEP_S:
        time.sleep(_REQUEST_SLEEP_S - elapsed)
    _last_request_at = time.monotonic()


def _retry_after_seconds(value: str | None, attempt: int) -> float:
    """Parse a ``Retry-After`` header value -- delay-seconds or an HTTP-date --
    falling back to the exponential backoff on anything unparsable. Never raises."""
    backoff = 2.0 * (attempt + 1)
    if not value:
        return backoff
    try:
        return float(value)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return backoff
    if when is None:
        return backoff
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max((when - datetime.now(timezone.utc)).total_seconds(), 0.0)


def _get_with_retry(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = _HTTP_TIMEOUT,
) -> httpx.Response | None:
    """GET with the same politeness + backoff as the SPARQL client: retries 429/5xx,
    honours ``Retry-After``, sleeps between tries. Returns ``None`` (never raises) once
    retries are exhausted, since a single candidate's network failure should not abort
    the whole fetch."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_TRIES):
        _throttle()
        try:
            resp = httpx.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout,
                verify=_client_verify(),
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(2.0 * (attempt + 1))
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            wait_s = _retry_after_seconds(retry_after, attempt)
            time.sleep(wait_s)
            last_exc = RuntimeError(f"{url} returned {resp.status_code}")
            continue
        return resp
    print(f"WARNING: request to {url} failed after {_MAX_TRIES} tries: {last_exc}")
    return None


def _sparql(query: str) -> list[dict[str, Any]]:
    """Run one SPARQL query against WDQS, retrying 429/5xx with backoff. Raises
    ``RuntimeError`` if the request never succeeds (including a WDQS-side timeout,
    which typically surfaces as a 500/504)."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    }
    resp = _get_with_retry(
        WDQS_URL,
        params={"query": query, "format": "json"},
        headers=headers,
        timeout=_SPARQL_TIMEOUT,
    )
    if resp is None:
        raise RuntimeError(f"SPARQL query failed after {_MAX_TRIES} tries")
    resp.raise_for_status()
    return resp.json()["results"]["bindings"]


def _sparql_or_none(query: str, *, what: str) -> list[dict[str, Any]] | None:
    """Like ``_sparql``, but reports (never raises) on failure -- the caller decides
    whether to fall back to a cheaper query shape. A 4xx such as a WDQS query-parse
    error surfaces as ``httpx.HTTPError`` from ``raise_for_status``, not
    ``RuntimeError``, so both are caught here."""
    try:
        return _sparql(query)
    except (RuntimeError, httpx.HTTPError) as exc:
        print(f"WARNING: {what} query failed ({exc})")
        return None


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


def _city_coord(qid: str) -> tuple[float, float] | None:
    """The city item's own P625, used as the centre for the --max-km place filter and
    for the radius fallback queries. Returns ``None`` (never raises) if the item has
    no P625 at all -- the caller must warn and skip radius-dependent features rather
    than silently treat an unresolved centre as "no distance to check"."""
    rows = _sparql_or_none(
        f"SELECT ?coord WHERE {{ wd:{qid} wdt:P625 ?coord }} LIMIT 1",
        what="city coordinate",
    )
    if not rows:
        return None
    return _parse_point(_val(rows[0], "coord"))


def _hotel_query(qid: str, limit: int) -> str:
    exclusions = "\n".join(
        f"      FILTER NOT EXISTS {{ ?item wdt:P31 wd:{c} . }}"
        for c in _EXCLUDED_ACCOMMODATION_CLASSES
    )
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?address ?districtLabel ?sitelinks ?enTitle
    WHERE {{
      VALUES ?class {{ {_class_values(_ACCOMMODATION_CLASSES)} }}
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


def _hotel_query_radius(
    city_coord: tuple[float, float], max_km: float, limit: int
) -> str:
    lat, lon = city_coord
    exclusions = "\n".join(
        f"      FILTER NOT EXISTS {{ ?item wdt:P31 wd:{c} . }}"
        for c in _EXCLUDED_ACCOMMODATION_CLASSES
    )
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?address ?districtLabel ?sitelinks ?enTitle
    WHERE {{
      VALUES ?class {{ {_class_values(_ACCOMMODATION_CLASSES)} }}
      ?item wdt:P31 ?class .
      SERVICE wikibase:around {{
        ?item wdt:P625 ?coord .
        bd:serviceParam wikibase:center "Point({lon} {lat})"^^geo:wktLiteral .
        bd:serviceParam wikibase:radius "{max_km}" .
      }}
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
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?address ?sitelinks ?enTitle ?classLabel
    WHERE {{
      VALUES ?class {{ {_class_values(_RESTAURANT_CLASSES)} }}
      ?item wdt:P31 ?class .
      ?item wdt:P131* wd:{qid} .
      ?item wdt:P625 ?coord .
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


def _items_query(qids: list[str]) -> str:
    """Named items with no usable P31 (e.g. Jeju Dongmun Traditional Market), added by
    ``--extra-restaurant``/``--extra-hotel``/``--extra-place``; everything else still
    comes from Wikidata."""
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?address ?sitelinks ?enTitle
    WHERE {{
      VALUES ?item {{ {values} }}
      ?item wdt:P625 ?coord .
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
    """


def _restaurant_query_radius(
    city_coord: tuple[float, float], max_km: float, limit: int
) -> str:
    lat, lon = city_coord
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?address ?sitelinks ?enTitle ?classLabel
    WHERE {{
      VALUES ?class {{ {_class_values(_RESTAURANT_CLASSES)} }}
      ?item wdt:P31 ?class .
      SERVICE wikibase:around {{
        ?item wdt:P625 ?coord .
        bd:serviceParam wikibase:center "Point({lon} {lat})"^^geo:wktLiteral .
        bd:serviceParam wikibase:radius "{max_km}" .
      }}
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
    """The distinct-item selection (with its LIMIT) is pushed into a subquery so
    ``limit`` bounds actual place *items*, not rows -- the place query joins each
    item against every one of its P31 values, so without the subquery an item with
    three instance-of statements consumed three rows of the LIMIT budget on its own.
    Exclusions are also collapsed from one FILTER NOT EXISTS per class into a single
    VALUES-driven one, which measurably cuts query cost on a large P131 hierarchy
    (Paris, Rome)."""
    excl_vals = _class_values(_EXCLUDED_PLACE_CLASSES)
    destroyed_vals = _class_values(_DESTROYED_STATE_OF_USE_CLASSES)
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?class ?classLabel ?sitelinks ?enTitle
    WHERE {{
      {{
        SELECT DISTINCT ?item ?coord ?image ?sitelinks WHERE {{
          ?item wdt:P131* wd:{qid} .
          FILTER (?item != wd:{qid})
          ?item wdt:P625 ?coord .
          ?item wdt:P18 ?image .
          ?item wdt:P31 ?anyClass .
          FILTER NOT EXISTS {{ ?item wdt:P31 ?exclClass . VALUES ?exclClass {{ {excl_vals} }} }}
          FILTER NOT EXISTS {{ ?item wdt:P5816 ?destroyedClass . VALUES ?destroyedClass {{ {destroyed_vals} }} }}
          ?item wikibase:sitelinks ?sitelinks .
        }}
        ORDER BY DESC(?sitelinks)
        LIMIT {limit}
      }}
      ?item wdt:P31 ?class .
      OPTIONAL {{
        ?enArticle schema:about ?item ;
                   schema:isPartOf <https://en.wikipedia.org/> ;
                   schema:name ?enTitle .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """


def _place_query_radius(
    qid: str, city_coord: tuple[float, float], max_km: float, limit: int
) -> str:
    """Fallback for a city whose P131 hierarchy is too large for WDQS to walk within
    its own query timeout (Paris, Rome): skip P131 entirely and search by distance."""
    lat, lon = city_coord
    excl_vals = _class_values(_EXCLUDED_PLACE_CLASSES)
    destroyed_vals = _class_values(_DESTROYED_STATE_OF_USE_CLASSES)
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?class ?classLabel ?sitelinks ?enTitle
    WHERE {{
      ?item wdt:P18 ?image .
      ?item wdt:P31 ?class .
      FILTER (?item != wd:{qid})
      SERVICE wikibase:around {{
        ?item wdt:P625 ?coord .
        bd:serviceParam wikibase:center "Point({lon} {lat})"^^geo:wktLiteral .
        bd:serviceParam wikibase:radius "{max_km}" .
      }}
      FILTER NOT EXISTS {{ ?item wdt:P31 ?exclClass . VALUES ?exclClass {{ {excl_vals} }} }}
      FILTER NOT EXISTS {{ ?item wdt:P5816 ?destroyedClass . VALUES ?destroyedClass {{ {destroyed_vals} }} }}
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


def _rewrite_to_upload_host(thumburl: str) -> str:
    """A Commons ``thumburl`` resolves through the ``thumb.wikimedia.org`` CDN host;
    rewrite it onto ``upload.wikimedia.org`` (same path shape) and drop the query
    string, per the schema's ``image_url`` contract."""
    parsed = urllib.parse.urlsplit(thumburl)
    return urllib.parse.urlunsplit(
        ("https", "upload.wikimedia.org", parsed.path, "", "")
    )


def _strip_query(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _resolve_commons_images(filenames: list[str]) -> dict[str, str]:
    """Resolve Commons file names to a real, query-string-free upload.wikimedia.org URL:
    a 1280px-wide thumb, or the original (query stripped) when it is already narrower
    than 1280px. SVGs get their thumbed ``.png`` suffix from Commons itself."""
    resolved: dict[str, str] = {}
    unique = sorted({f for f in filenames if f})
    headers = {"User-Agent": USER_AGENT}
    for batch in _chunks(unique, 50):
        titles = "|".join(f"File:{name}" for name in batch)
        resp = _get_with_retry(
            COMMONS_API,
            params={
                "action": "query",
                "titles": titles,
                "prop": "imageinfo",
                "iiprop": "url|size",
                "iiurlwidth": 1280,
                "format": "json",
            },
            headers=headers,
        )
        if resp is None:
            continue
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")
            infos = page.get("imageinfo") or []
            if not infos or not title.startswith("File:"):
                continue
            info = infos[0]
            thumburl = info.get("thumburl")
            full_url = info.get("url")
            thumb_width = info.get("thumbwidth")
            width = info.get("width")
            if thumburl and thumb_width and width and width > thumb_width:
                url = _rewrite_to_upload_host(thumburl)
            elif full_url:
                url = _strip_query(full_url)
            elif thumburl:
                url = _rewrite_to_upload_host(thumburl)
            else:
                continue
            resolved[title[len("File:") :]] = url
    return resolved


def _fetch_wikipedia_summary(title: str, qid: str) -> dict[str, str] | None:
    """Fetch the summary for the item's own enwiki sitelink title, and drop it unless
    the response's own ``wikibase_item`` matches ``qid``: a sitelink title can still
    redirect Wikipedia-side to a different article about a different Wikidata item
    (this is exactly how a restaurant with no enwiki article at all previously picked
    up an unrelated "Drug withdrawal" extract via its label, and how a building's own
    sitelink title redirected to its neighbouring landmark's article)."""
    headers = {"User-Agent": USER_AGENT}
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    resp = _get_with_retry(
        WIKIPEDIA_SUMMARY_URL.format(title=encoded),
        headers=headers,
    )
    if resp is None or resp.status_code != 200:
        return None
    data = resp.json()
    extract = data.get("extract")
    if not extract:
        return None
    if data.get("wikibase_item") != qid:
        return None
    return {"title": data.get("title", title), "extract": extract}


def _wikitext_to_plain(text: str) -> str:
    # File:/Image: links and <gallery> blocks carry no prose -- drop them whole,
    # before the generic wikilink regex below (which would otherwise keep their
    # "thumb|Caption"-style trailing segment as if it were the link's label).
    text = re.sub(
        r"<gallery[^>]*>.*?</gallery>", "", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)  # one more pass for shallow nesting
    # External links: "[https://... label]" keeps the label; a bare "[https://...]"
    # (no label) is dropped entirely rather than left as a stray URL.
    text = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\]", "", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^\*+\s*", "- ", text, flags=re.MULTILINE)
    # Leftover "thumb|" fragments from an image markup pattern this pass doesn't
    # otherwise reach (e.g. inside a template argument already partly stripped).
    text = re.sub(r"\bthumb\|", "", text, flags=re.IGNORECASE)
    text = html.unescape(text)  # &mdash; and friends
    # "- - -" residue left behind by a stripped template (e.g. a horizontal-rule or
    # infobox-row template whose only visible content was dashes).
    text = re.sub(r"(?:-\s+){2,}-", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:_WIKIVOYAGE_SECTION_CHAR_CAP]


def _extract_sections(wikitext: str, names: tuple[str, ...]) -> dict[str, str | None]:
    """Slice each wanted heading to the next heading of the *same or higher* level
    (fewer or equal ``=`` characters), so its subsections (e.g. "Eat" -> "Budget" /
    "Mid-range" / "Splurge", "Get around" -> "By train") are kept rather than cut at
    the first subsection boundary. A heading that exists but whose body is only
    templates/links (nothing left after ``_wikitext_to_plain``) is recorded as an
    empty string; a heading that does not exist at all is recorded as ``None`` --
    the two are not the same and callers should not conflate them."""
    heading_re = re.compile(r"^(=+)\s*([^=]+?)\s*=+\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(wikitext))
    sections: dict[str, str | None] = dict.fromkeys(names, None)
    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        if heading not in names:
            continue
        start = m.end()
        end = len(wikitext)
        for later in matches[i + 1 :]:
            if len(later.group(1)) <= level:
                end = later.start()
                break
        sections[heading] = _wikitext_to_plain(wikitext[start:end])
    return sections


def _wikivoyage_page_title(qid: str, city: str) -> str:
    """The city's own enwikivoyage sitelink title, when it differs from the CLI city
    name (e.g. New York, Q60 -> "New York City"): resolving by QID avoids a 0-section
    fetch against a page that does not exist under the bare city name."""
    headers = {"User-Agent": USER_AGENT}
    resp = _get_with_retry(
        WIKIDATA_API,
        params={
            "action": "wbgetentities",
            "ids": qid,
            "props": "sitelinks",
            "sitefilter": "enwikivoyage",
            "format": "json",
        },
        headers=headers,
    )
    if resp is None or resp.status_code != 200:
        return city
    entity = resp.json().get("entities", {}).get(qid, {})
    title = entity.get("sitelinks", {}).get("enwikivoyage", {}).get("title")
    return title or city


def _fetch_wikivoyage_sections(qid: str, city: str) -> dict[str, str | None]:
    page_title = _wikivoyage_page_title(qid, city)
    headers = {"User-Agent": USER_AGENT}
    resp = _get_with_retry(
        WIKIVOYAGE_API,
        params={
            "action": "parse",
            "page": page_title,
            "prop": "wikitext",
            "format": "json",
        },
        headers=headers,
    )
    if resp is None or resp.status_code != 200:
        return dict.fromkeys(_WIKIVOYAGE_SECTIONS, None)
    data = resp.json()
    wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
    if not wikitext:
        return dict.fromkeys(_WIKIVOYAGE_SECTIONS, None)
    return _extract_sections(wikitext, _WIKIVOYAGE_SECTIONS)


def _build_hotel_like_entries(
    rows_with_strategy: list[tuple[dict[str, Any], str]],
    image_map: dict[str, str],
) -> list[dict[str, Any]]:
    """One entry per distinct QID, first occurrence wins (P131 rows are always listed
    before radius-fallback rows, so a hotel/restaurant found both ways keeps its
    ``p131`` strategy tag). ``instance_of`` is kept when the row carries a
    ``classLabel`` (the restaurant query does, to show curation a market/bakery/pub
    result is not a plain restaurant)."""
    by_qid: dict[str, dict[str, Any]] = {}
    for row, strategy in rows_with_strategy:
        qid = _qid_from_uri(_val(row, "item"))
        if not qid or qid in by_qid:
            continue
        point = _parse_point(_val(row, "coord"))
        filename = _filename_from_p18(_val(row, "image"))
        image_url = image_map.get(filename) if filename else None
        class_label = _val(row, "classLabel")
        by_qid[qid] = {
            "qid": qid,
            "label": _val(row, "itemLabel"),
            "latitude": point[0] if point else None,
            "longitude": point[1] if point else None,
            "image_url": image_url,
            "address": _val(row, "address") or _val(row, "districtLabel"),
            "sitelinks": int(float(_val(row, "sitelinks") or 0)),
            "en_title": _val(row, "enTitle"),
            "strategy": strategy,
            "instance_of": [class_label] if class_label else [],
        }
    return sorted(by_qid.values(), key=lambda e: e["sitelinks"], reverse=True)


def _merge_by_qid(
    primary: list[dict[str, Any]], extra: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen = {e["qid"] for e in primary}
    merged = list(primary)
    for entry in extra:
        if entry["qid"] not in seen:
            merged.append(entry)
            seen.add(entry["qid"])
    return merged


def _build_place_entries(
    rows: list[dict[str, Any]],
    image_map: dict[str, str],
    city_coord: tuple[float, float] | None,
    max_km: float,
    strategy: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    dropped_far = 0
    for row in _merge_place_rows(rows):
        point = _parse_point(row["coord"])
        if city_coord and point:
            distance = haversine_km(city_coord[0], city_coord[1], point[0], point[1])
            if distance > max_km:
                dropped_far += 1
                print(
                    f"NOTE: dropping {row['label']!r} ({row['qid']}): "
                    f"{distance:.1f} km from city centre, exceeds --max-km {max_km}"
                )
                continue
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
                "strategy": strategy,
            }
        )
    if dropped_far:
        print(f"NOTE: dropped {dropped_far} place(s) beyond --max-km {max_km}")
    return entries


def fetch_city_candidates(
    city: str,
    qid: str,
    hotel_limit: int = 40,
    place_limit: int = 60,
    restaurant_limit: int = 30,
    max_km: float = _DEFAULT_MAX_KM,
    extra_restaurants: tuple[str, ...] = (),
    extra_hotels: tuple[str, ...] = (),
    extra_places: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Fetch and assemble one city's candidate file. Returns the JSON-ready dict."""
    city_coord = _city_coord(qid)
    if city_coord is None:
        print(
            f"WARNING: {city} ({qid}) has no resolvable P625 coordinate; the "
            f"--max-km {max_km} distance filter, the hotel/restaurant/place radius "
            "fallback and the landmark_image fallback are all skipped"
        )

    hotel_p131_rows = (
        _sparql_or_none(_hotel_query(qid, hotel_limit), what="hotel") or []
    )
    hotel_rows_with_strategy = [(r, "p131") for r in hotel_p131_rows]
    n_hotel_qids = len({_qid_from_uri(_val(r, "item")) for r in hotel_p131_rows})
    if n_hotel_qids < _MIN_HOTELS_BEFORE_RADIUS_FALLBACK and city_coord:
        print(
            f"NOTE: only {n_hotel_qids} P131-chained hotel(s); running a "
            f"--max-km {max_km} radius search too"
        )
        radius_rows = (
            _sparql_or_none(
                _hotel_query_radius(city_coord, max_km, hotel_limit),
                what="hotel radius",
            )
            or []
        )
        hotel_rows_with_strategy += [(r, "radius") for r in radius_rows]

    if extra_hotels:
        manual_rows = (
            _sparql_or_none(_items_query(list(extra_hotels)), what="extra items") or []
        )
        hotel_rows_with_strategy += [(r, "manual") for r in manual_rows]

    restaurant_p131_rows = (
        _sparql_or_none(_restaurant_query(qid, restaurant_limit), what="restaurant")
        or []
    )
    restaurant_rows_with_strategy = [(r, "p131") for r in restaurant_p131_rows]
    n_restaurant_qids = len(
        {_qid_from_uri(_val(r, "item")) for r in restaurant_p131_rows}
    )
    if n_restaurant_qids < _MIN_RESTAURANTS_BEFORE_RADIUS_FALLBACK and city_coord:
        print(
            f"NOTE: only {n_restaurant_qids} P131-chained restaurant(s); running a "
            f"--max-km {max_km} radius search too"
        )
        radius_rows = (
            _sparql_or_none(
                _restaurant_query_radius(city_coord, max_km, restaurant_limit),
                what="restaurant radius",
            )
            or []
        )
        restaurant_rows_with_strategy += [(r, "radius") for r in radius_rows]

    if extra_restaurants:
        manual_rows = (
            _sparql_or_none(_items_query(list(extra_restaurants)), what="extra items")
            or []
        )
        restaurant_rows_with_strategy += [(r, "manual") for r in manual_rows]

    place_rows = _sparql_or_none(_place_query(qid, place_limit), what="place")
    place_strategy = "p131"
    if place_rows is None:
        place_strategy = "radius"
        if city_coord:
            place_rows = (
                _sparql_or_none(
                    _place_query_radius(qid, city_coord, max_km, place_limit),
                    what="place radius",
                )
                or []
            )
        else:
            place_rows = []

    if extra_places:
        manual_place_rows = (
            _sparql_or_none(_items_query(list(extra_places)), what="extra items") or []
        )
        place_rows = (place_rows or []) + manual_place_rows

    all_rows = (
        [r for r, _ in hotel_rows_with_strategy]
        + [r for r, _ in restaurant_rows_with_strategy]
        + place_rows
    )
    filenames = [
        f for f in (_filename_from_p18(_val(r, "image")) for r in all_rows) if f
    ]
    image_map = _resolve_commons_images(filenames)

    hotels = _build_hotel_like_entries(hotel_rows_with_strategy, image_map)
    restaurants = _build_hotel_like_entries(restaurant_rows_with_strategy, image_map)
    places = _build_place_entries(
        place_rows, image_map, city_coord, max_km, place_strategy
    )
    if extra_places:
        manual_qids = set(extra_places)
        for entry in places:
            if entry["qid"] in manual_qids:
                entry["strategy"] = "manual"

    wikipedia: dict[str, dict[str, str]] = {}
    for entry in hotels + places + restaurants:
        # Only ever the item's own enwiki sitelink title -- never the Wikidata label,
        # which for an item with no enwiki article at all can coincidentally match an
        # unrelated Wikipedia page title (see _fetch_wikipedia_summary docstring).
        title = entry.get("en_title")
        if not title or entry["qid"] in wikipedia:
            continue
        summary = _fetch_wikipedia_summary(title, entry["qid"])
        if summary:
            wikipedia[entry["qid"]] = summary

    wikivoyage = _fetch_wikivoyage_sections(qid, city)

    landmark_image: str | None = None
    if city_coord:
        city_image_rows = _sparql_or_none(
            f"SELECT ?image WHERE {{ wd:{qid} wdt:P18 ?image }} LIMIT 1",
            what="city landmark image",
        )
        if city_image_rows:
            city_filename = _filename_from_p18(_val(city_image_rows[0], "image"))
            if city_filename:
                city_image_map = _resolve_commons_images([city_filename])
                landmark_image = city_image_map.get(city_filename)

    strategies_used = {
        "hotels": sorted({e["strategy"] for e in hotels}),
        "places": [place_strategy],
        "restaurants": sorted({e["strategy"] for e in restaurants}),
    }

    return {
        "city": city,
        "wikidata_qid": qid,
        "max_km": max_km if city_coord is not None else None,
        "strategies": strategies_used,
        "hotels": hotels,
        "places": places,
        "restaurants": restaurants,
        "landmark_image": landmark_image,
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
    parser.add_argument(
        "--max-km",
        type=float,
        default=_DEFAULT_MAX_KM,
        help=(
            "Drop any place candidate farther than this from the city's own P625 "
            f"(default {_DEFAULT_MAX_KM}; a sprawling metro like LA or Sydney may need 25)"
        ),
    )
    parser.add_argument(
        "--extra-restaurant",
        action="append",
        default=[],
        metavar="QID",
        help="Add a named food item that has no usable P31 (repeatable)",
    )
    parser.add_argument(
        "--extra-hotel",
        action="append",
        default=[],
        metavar="QID",
        help="Add a named hotel that has no usable P31 (repeatable)",
    )
    parser.add_argument(
        "--extra-place",
        action="append",
        default=[],
        metavar="QID",
        help=(
            "Add a named place that has no usable P31 (repeatable); still subject "
            "to --max-km"
        ),
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.city}.json"

    data = fetch_city_candidates(
        args.city,
        args.qid,
        max_km=args.max_km,
        extra_restaurants=tuple(args.extra_restaurant),
        extra_hotels=tuple(args.extra_hotel),
        extra_places=tuple(args.extra_place),
    )
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    n_hotels = len(data["hotels"])
    n_places = len(data["places"])
    n_restaurants = len(data["restaurants"])
    print(
        f"{args.city}: {n_hotels} hotels, {n_places} places, "
        f"{n_restaurants} restaurants -> {out_path}"
    )

    shortfalls = []
    if n_hotels < 6:
        shortfalls.append(f"hotels ({n_hotels} < 6)")
    if n_places < 8:
        shortfalls.append(f"places ({n_places} < 8)")
    if n_restaurants < 2:
        shortfalls.append(f"restaurants ({n_restaurants} < 2)")
    if shortfalls:
        print(f"WARNING: below minimum coverage: {', '.join(shortfalls)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
