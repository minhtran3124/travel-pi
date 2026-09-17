"""Idempotent seeder: upsert the read-only ``app/data`` reference entities into the DB via SQLAlchemy ORM."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select

from app.data.agent_config import AGENT_CONFIG_NODES
from app.data.airlines import AIRLINE_COLORS, AIRLINES
from app.data.airports import AIRPORTS
from app.data.cities import CITIES
from app.data.countries import COUNTRIES
from app.data.fx import (
    COUNTRY_CURRENCY,
    CURRENCY_NAMES,
    LAST_UPDATED,
    RATES,
)
from app.data.hotels import HOTELS
from app.data.places import PLACES
from app.data.tips import CITY_TIPS, COUNTRY_SUMMARIES, COUNTRY_TIPS
from app.data.visa import COUNTRY_VISA
from app.db import models
from app.db.base import deterministic_uuid
from app.schemas.hotel import Hotel as HotelSchema
from app.schemas.place import Place as PlaceSchema

logger = logging.getLogger(__name__)


def _seed_countries(session) -> None:
    # Store the curated COUNTRIES order as ``position`` so the repo can ORDER BY it.
    for i, c in enumerate(COUNTRIES):
        session.merge(
            models.Country(
                id=deterministic_uuid("country", c["code"]),
                code=c["code"],
                name=c["name"],
                region=c["region"],
                position=i,
                latitude=c["latitude"],
                longitude=c["longitude"],
            )
        )


def _seed_airlines(session) -> None:
    # AIRLINES order is load-bearing for flight determinism → store as ``position``.
    for i, a in enumerate(AIRLINES):
        session.merge(
            models.Airline(
                id=deterministic_uuid("airline", a["code"]),
                code=a["code"],
                name=a["name"],
                position=i,
                color=AIRLINE_COLORS.get(a["code"]),
            )
        )


def _seed_airports(session) -> None:
    # ``position`` records AIRPORTS insertion order so the repo can ORDER BY it.
    for i, (iata, info) in enumerate(AIRPORTS.items()):
        session.merge(
            models.Airport(
                id=deterministic_uuid("airport", iata),
                iata=iata,
                name=info["name"],
                city=info["city"],
                country=info["country"],
                country_code=info["country_code"],
                position=i,
            )
        )


def _seed_cities(session) -> None:
    # City has an autoincrement int PK → merge would duplicate on re-run; upsert by (name, country).
    name_to_code = {c["name"]: c["code"] for c in COUNTRIES}
    for c in CITIES:
        existing = session.scalar(
            select(models.City).where(
                models.City.name == c["name"],
                models.City.country == c["country"],
            )
        )
        country_code = name_to_code.get(c["country"])
        if existing is not None:
            existing.country_code = country_code
            existing.airport_codes = c["airport_codes"]
            existing.latitude = c.get("latitude")
            existing.longitude = c.get("longitude")
        else:
            session.add(
                models.City(
                    id=deterministic_uuid("city", c["name"], c["country"]),
                    name=c["name"],
                    country=c["country"],
                    country_code=country_code,
                    airport_codes=c["airport_codes"],
                    latitude=c.get("latitude"),
                    longitude=c.get("longitude"),
                )
            )


def _seed_hotels(session) -> None:
    # ``country`` is already on each record — map straight, do NOT re-derive.
    for i, h in enumerate(HOTELS):
        session.merge(
            models.Hotel(
                id=h["id"],
                position=i,
                code=h["code"],
                name=h["name"],
                city=h["city"],
                country=h["country"],
                address=h["address"],
                star_rating=h["star_rating"],
                price_per_night=h["price_per_night"],
                currency=h["currency"],
                amenities=h["amenities"],
                image_url=h["image_url"],
                rating=h["rating"],
                review_count=h["review_count"],
                description=h["description"],
                property_type=h["property_type"],
                chain=h["chain"],
                check_in_time=h["check_in_time"],
                check_out_time=h["check_out_time"],
                breakfast_included=h["breakfast_included"],
                free_cancellation=h["free_cancellation"],
                languages_spoken=h["languages_spoken"],
            )
        )


def _seed_places(session) -> None:
    for i, p in enumerate(PLACES):
        session.merge(
            models.Place(
                id=p["id"],
                position=i,
                name=p["name"],
                city=p["city"],
                country=p["country"],
                category=p["category"],
                description=p["description"],
                address=p["address"],
                rating=p["rating"],
                review_count=p["review_count"],
                price_level=p["price_level"],
                opening_hours=p.get("opening_hours"),
                image_url=p["image_url"],
                tags=p["tags"],
                is_recommended=p.get("is_recommended", False),
                latitude=p.get("latitude"),
                longitude=p.get("longitude"),
            )
        )


def _seed_tips(session) -> None:
    def _emit(records: list[dict], scope: str, location: str) -> None:
        for i, r in enumerate(records):
            session.merge(
                models.Tip(
                    id=deterministic_uuid("tip", scope, location, str(i)),
                    scope=scope,
                    key=location,
                    position=i,
                    category=r["category"],
                    title=r["title"],
                    content=r["content"],
                    is_essential=r.get("is_essential", False),
                )
            )

    for country, records in COUNTRY_TIPS.items():
        _emit(records, "country", country)
    for city, records in CITY_TIPS.items():
        _emit(records, "city", city)

    for country, summary in COUNTRY_SUMMARIES.items():
        session.merge(
            models.CountrySummary(
                id=deterministic_uuid("country_summary", country),
                country=country,
                summary=summary,
            )
        )


def _seed_visa(session) -> None:
    for country, v in COUNTRY_VISA.items():
        session.merge(
            models.Visa(
                id=deterministic_uuid("visa", country),
                country=country,
                visa_free_days=v["visa_free_days"],
                visa_on_arrival=v["visa_on_arrival"],
                e_visa=v["e_visa"],
                passport_validity_months=v["passport_validity_months"],
                summary=v["summary"],
            )
        )


def _seed_fx(session) -> None:
    for code, rate in RATES.items():
        session.merge(
            models.FxRate(
                id=deterministic_uuid("fxrate", code),
                code=code,
                rate=rate,
                name=CURRENCY_NAMES.get(code, code),
            )
        )
    for country, code in COUNTRY_CURRENCY.items():
        session.merge(
            models.CountryCurrency(
                id=deterministic_uuid("country_currency", country),
                country=country,
                code=code,
            )
        )
    session.merge(
        models.FxMeta(
            id=deterministic_uuid("fx_meta", "singleton"),
            last_updated=LAST_UPDATED,
        )
    )


def _seed_agent_config(session) -> None:
    # agent_name is a natural key with an auto UUID PK → upsert by lookup, not merge.
    for name in AGENT_CONFIG_NODES:
        existing = session.scalar(
            select(models.AgentConfig).where(models.AgentConfig.agent_name == name)
        )
        if existing is None:
            session.add(models.AgentConfig(agent_name=name))


def _check_short_code_collisions(session) -> None:
    """Fail loudly if two hotels/places hash to the same short_code."""
    hotel_index: dict[str, str] = {}
    for row in session.scalars(select(models.Hotel)):
        hotel = HotelSchema.model_validate(row, from_attributes=True)
        existing = hotel_index.get(hotel.short_code)
        if existing is not None:
            raise RuntimeError(
                f"Hotel short-code collision: {hotel.short_code} maps to "
                f"both {existing!r} and {hotel.id!r}"
            )
        hotel_index[hotel.short_code] = hotel.id

    place_index: dict[str, str] = {}
    for row in session.scalars(select(models.Place)):
        place = PlaceSchema.model_validate(row, from_attributes=True)
        existing = place_index.get(place.short_code)
        if existing is not None:
            raise RuntimeError(
                f"Place short-code collision: {place.short_code} maps to "
                f"both {existing!r} and {place.id!r}"
            )
        place_index[place.short_code] = place.id


# Checked-in catalog translations, one file per language; absent/empty seeds nothing.
_TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "data"
_TRANSLATIONS_GLOB = "content_translations.*.json"


def _seed_content_translations(session) -> int:
    """Upsert every checked-in catalog translation; returns the number of rows written."""
    from app.core.languages import normalize
    from app.repositories.content_translation import ContentTranslationRepo

    rows: list[dict] = []
    for path in sorted(_TRANSLATIONS_DIR.glob(_TRANSLATIONS_GLOB)):
        language = path.name.split(".")[1]
        if normalize(language) != language:
            raise RuntimeError(f"unsupported translation language file: {path.name}")
        for rec in json.loads(path.read_text()):
            rows.append(
                {
                    "entity_type": rec["entity_type"],
                    "entity_id": rec["entity_id"],
                    "field": rec["field"],
                    "language": language,
                    "text": rec["text"],
                    "source": "seed",
                }
            )
    return ContentTranslationRepo(session).upsert_many(rows)


def seed_all(session_factory) -> None:
    """Seed every reference entity into the DB behind ``session_factory``; idempotent, commits once."""
    with session_factory() as session:
        _seed_countries(session)
        _seed_airlines(session)
        _seed_airports(session)
        _seed_cities(session)
        _seed_hotels(session)
        _seed_places(session)
        _seed_tips(session)
        _seed_visa(session)
        _seed_fx(session)
        _seed_agent_config(session)
        _seed_content_translations(session)
        session.flush()
        _check_short_code_collisions(session)
        session.commit()
    logger.info("Seeded reference data from app/data")
