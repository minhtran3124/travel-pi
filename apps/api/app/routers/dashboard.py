"""Server-rendered Jinja2 dashboard pages (HTML), excluded from the OpenAPI schema."""

from datetime import UTC, date, datetime, timedelta
from math import ceil
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.agents.metrics import MAX_STEPS_PER_TURN as _MAX_STEPS_PER_TURN
from app.core.dashboard_auth import get_current_dashboard_user
from app.core.languages import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, normalize
from app.core.llm_providers import LLM_PROVIDERS, PROVIDER_NAMES
from app.core.params import parse_optional_number
from app.core.pricing import is_priced
from app.db import models
from app.db.session import get_session
from app.exceptions import (
    CityNotFoundError,
    DomainValidationError,
    NotFoundError,
    WeatherUnavailableError,
)
from app.repositories.agent_run import AgentRunRepository
from app.repositories.airline import AIRLINE_COLOR_DEFAULT, AirlineRepository
from app.repositories.city import CityRepository
from app.repositories.country import CountryRepository
from app.repositories.tip import TipRepository
from app.repositories.visa import VisaRepository
from app.routers.tags import Tags
from app.services import (
    air_quality_service,
    board_service,
    flight_service,
    weather_service,
)
from app.services.agent_config_service import AgentConfigService
from app.services.airport_service import AirportService
from app.services.board_service import BoardService
from app.services.booking_service import BOOKING_SORTS, BookingService
from app.services.content_translation_service import ContentTranslationService
from app.services.flight_service import FlightService
from app.services.hotel_service import HotelService
from app.services.place_service import PlaceService
from app.services.tip_service import TipService
from app.services.visa_service import VisaService
from app.streaming.panels.places import CATEGORY_VI

router = APIRouter(
    prefix="/dashboard",
    tags=[Tags.dashboard],
    include_in_schema=False,
    dependencies=[Depends(get_current_dashboard_user)],
)

# Path relative to this file so it works regardless of the current working directory.
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# 221 -> "3h41m".
_TEMPLATES.env.filters["hm"] = lambda minutes: f"{minutes // 60}h{minutes % 60:02d}m"

_DEFAULT_AIRPORT = "SGN"

# ``?lang=`` wins, else the cookie set by an earlier choice, else the default.
_LANG_COOKIE = "dashboard_lang"
_TEMPLATES.env.globals["supported_languages"] = SUPPORTED_LANGUAGES


def _dashboard_language(request: Request, lang: str | None) -> str:
    """Resolve the catalog language for this request (``?lang=`` then cookie)."""
    return normalize(lang or request.cookies.get(_LANG_COOKIE))


def _remember_language(response: Response, lang: str | None, resolved: str) -> None:
    """Persist an explicit ``?lang=`` choice so the next page keeps it."""
    if lang:
        response.set_cookie(
            _LANG_COOKIE, resolved, max_age=365 * 24 * 3600, samesite="lax"
        )


@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard_index(request: Request) -> HTMLResponse:
    """Render the dashboard landing page."""
    return _TEMPLATES.TemplateResponse(request=request, name="index.html")


@router.get("/_search.json", include_in_schema=False)
def palette_index(
    session: Annotated[Session, Depends(get_session)],
) -> JSONResponse:
    """Lightweight index for the command palette (cities + airports)."""
    city_repo = CityRepository(session)
    cities = sorted(
        {(city.name, city.country) for city in city_repo.list_with_counts()}
    )
    airports = AirportService(session).list_airports()
    return JSONResponse(
        {
            "cities": [{"name": n, "country": ct} for n, ct in cities],
            "airports": [{"code": a.code, "city": a.city} for a in airports],
        }
    )


@router.get("/flights", response_class=HTMLResponse)
def flight_board(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    airport: str | None = Query(None, description="IATA code of the board's airport"),
    date: str | None = Query(None, description="Board date, YYYY-MM-DD"),
    mode: str = Query("arrivals", description="'arrivals' or 'departures'"),
) -> HTMLResponse:
    """Render the main flight board for one airport and date (default: today's arrivals at the hub)."""
    airports_svc = AirportService(session)
    if mode not in (board_service.ARRIVALS, board_service.DEPARTURES):
        mode = board_service.ARRIVALS
    # Fall back to the default for unknown codes.
    board_airport = airports_svc.get_airport(
        airport or _DEFAULT_AIRPORT
    ) or airports_svc.get_airport(_DEFAULT_AIRPORT)
    board_date = date or _today()

    rows: list = []
    error: str | None = None
    try:
        rows = BoardService(session).build_board(board_airport.code, board_date, mode)
    except ValueError:
        error = "Invalid date — please use the date picker."

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="board.html",
        context={
            "airports": airports_svc.list_airports(),
            "airport": board_airport,
            "date": board_date,
            "mode": mode,
            "rows": rows,
            "error": error,
            "now": datetime.now().strftime("%H:%M"),
        },
    )


@router.get("/flights/search", response_class=HTMLResponse)
def flight_search(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    origin: str | None = Query(None),
    destination: str | None = Query(None),
    departure_date: str | None = Query(None),
    airline: str | None = Query(None),
    max_price: str | None = Query(None),
    max_stops: str | None = Query(None),
    sort: str = Query(flight_service.DEFAULT_SORT),
) -> HTMLResponse:
    """Render the optional 'search by route' page.

    Numeric filters arrive as raw strings so an empty form field (``""``) means
    "not filtered" and a non-numeric value shows a friendly error rather than a 422.
    """
    flight_svc = FlightService(session)
    airline_repo = AirlineRepository(session)
    airports = AirportService(session).list_airports()

    max_price_val, err_price = parse_optional_number(
        max_price, label="Max price", kind=float, minimum=0
    )
    max_stops_val, err_stops = parse_optional_number(
        max_stops, label="Max stops", kind=int, minimum=0
    )
    error: str | None = err_price or err_stops

    search = {
        "origin": (origin or "").upper() or None,
        "destination": (destination or "").upper() or None,
        "departure_date": departure_date or None,
        "airline": (airline or "").upper() or None,
        "max_price": max_price_val,
        "max_stops": max_stops_val,
        "sort": sort,
    }
    searched = all((search["origin"], search["destination"], search["departure_date"]))

    flights: list = []
    if searched and error is None:
        try:
            flights = flight_svc.search_flights(
                search["origin"],
                search["destination"],
                search["departure_date"],
                airline=search["airline"],
                max_price=max_price_val,
                max_stops=max_stops_val,
                sort=sort,
            )
        except ValueError:
            error = "Invalid date — please use the date picker."

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "airports": airports,
            "airports_by_code": {a.code: a for a in airports},
            "airlines": flight_svc.list_airlines(),
            "airline_colors": airline_repo.colors(),
            "airline_color_default": AIRLINE_COLOR_DEFAULT,
            "sort_options": flight_svc.sort_options(),
            "search": search,
            "searched": searched,
            "flights": flights,
            "error": error,
        },
    )


@router.get("/flights/{flight_id}", response_class=HTMLResponse)
def flight_detail_page(
    request: Request,
    flight_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """Render the detail page for a single flight.

    An unresolved ID renders a friendly "not found" template but still returns HTTP 200.
    """
    flight = FlightService(session).find_flight_by_id(flight_id)
    airports = AirportService(session).list_airports()
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="flight_detail.html",
        context={
            "flight": flight,
            "flight_id": flight_id,
            "airports_by_code": {a.code: a for a in airports},
            "airline_colors": AirlineRepository(session).colors(),
            "airline_color_default": AIRLINE_COLOR_DEFAULT,
        },
    )


# Sort options for the hotel grid. ``None`` means "leave in seed order".
_HOTEL_SORTS = {
    "featured": None,
    "rating_desc": lambda hotel: -hotel.rating,
    "rating_asc": lambda hotel: hotel.rating,
    "price_asc": lambda hotel: hotel.price_per_night,
    "price_desc": lambda hotel: -hotel.price_per_night,
    "name": lambda hotel: hotel.name.lower(),
}


@router.get("/hotels", response_class=HTMLResponse)
def hotel_list_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    city: str | None = Query(None, description="Filter the grid to one city"),
    q: str | None = Query(None, description="Case-insensitive hotel name search"),
    sort: str = Query("featured", description="Sort order; see _HOTEL_SORTS keys"),
    lang: str | None = Query(None, description="Catalog text language (en/vi)"),
) -> HTMLResponse:
    """Render the browsable hotel grid."""
    hotel_svc = HotelService(session)
    all_hotels = hotel_svc.list_hotels()
    cities = sorted({hotel.city for hotel in all_hotels})

    selected_city = city or None
    hotels = (
        hotel_svc.search_hotels(selected_city) if selected_city else list(all_hotels)
    )

    query = (q or "").strip()
    if query:
        needle = query.lower()
        hotels = [hotel for hotel in hotels if needle in hotel.name.lower()]

    if sort not in _HOTEL_SORTS:
        sort = "featured"
    sort_key = _HOTEL_SORTS[sort]
    if sort_key is not None:
        hotels = sorted(hotels, key=sort_key)

    language = _dashboard_language(request, lang)
    # Stored translations only: the dashboard never triggers a translator call.
    hotels = ContentTranslationService(session).localize(
        "hotel", hotels, ["description"], language, fill_misses=False
    )

    response = _TEMPLATES.TemplateResponse(
        request=request,
        name="hotels.html",
        context={
            "hotels": hotels,
            "cities": cities,
            "selected_city": selected_city,
            "query": query,
            "sort": sort,
            "total": len(all_hotels),
            "lang": language,
        },
    )
    _remember_language(response, lang, language)
    return response


_PLACE_SORTS = {
    "rating_desc": "Top Rated",
    "rating_asc": "Lowest Rated",
    "name": "Name A–Z",
    "price_asc": "Price: Low to High",
    "price_desc": "Price: High to Low",
    "reviews_desc": "Most Reviewed",
}

_PLACE_CATEGORIES = {
    "attraction": "Attraction",
    "restaurant": "Restaurant",
    "cafe": "Café",
    "activity": "Activity",
    "nightlife": "Nightlife",
    "shopping": "Shopping",
}

_PRICE_LABELS = {1: "Free / Cheap", 2: "Moderate", 3: "Expensive", 4: "Luxury"}


@router.get("/places", response_class=HTMLResponse)
def places_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    city: str | None = Query(None, description="Filter by city"),
    category: str | None = Query(None, description="Filter by category"),
    min_rating: str | None = Query(None, description="Minimum rating"),
    price_level: str | None = Query(None, description="Price level 1–4"),
    recommended: bool = Query(False, description="Recommended only"),
    sort: str = Query("rating_desc"),
    lang: str | None = Query(None, description="Catalog text language (en/vi)"),
) -> HTMLResponse:
    """Render the browsable places/attractions grid.

    ``min_rating`` and ``price_level`` are strings so an empty form field ("Any")
    maps to ``None`` rather than raising a 422.
    """
    if sort not in _PLACE_SORTS:
        sort = "rating_desc"

    # Bad numeric input renders a friendly inline message instead of 500'ing.
    min_rating_val, err_rating = parse_optional_number(
        min_rating, label="Min rating", kind=float, minimum=0, maximum=5
    )
    price_level_val, err_price = parse_optional_number(
        price_level, label="Price level", kind=int, minimum=1, maximum=4
    )
    error: str | None = err_rating or err_price

    place_svc = PlaceService(session)
    all_places = place_svc.list_places()
    cities = place_svc.cities()

    # Skip the search on bad input so the page shows the error, not a misleading "everything" list.
    results = (
        []
        if error
        else place_svc.search_places(
            city=city or None,
            category=category or None,
            min_rating=min_rating_val,
            price_level=price_level_val,
            recommended_only=recommended,
            sort=sort,
        )
    )

    language = _dashboard_language(request, lang)
    results = ContentTranslationService(session).localize(
        "place", results, ["description"], language, fill_misses=False
    )
    categories = (
        {k: CATEGORY_VI.get(k, v) for k, v in _PLACE_CATEGORIES.items()}
        if language != DEFAULT_LANGUAGE
        else _PLACE_CATEGORIES
    )

    response = _TEMPLATES.TemplateResponse(
        request=request,
        name="places.html",
        context={
            "places": results,
            "total": len(all_places),
            "cities": cities,
            "categories": categories,
            "lang": language,
            "price_labels": _PRICE_LABELS,
            "sort_options": _PLACE_SORTS,
            "selected_city": city or None,
            "selected_category": category or None,
            "selected_min_rating": min_rating_val,
            "selected_price_level": price_level_val,
            "recommended": recommended,
            "sort": sort,
            "error": error,
        },
    )
    _remember_language(response, lang, language)
    return response


def _city_country_map(session: Session) -> dict[str, str]:
    """City → country map that links the Local Tips / Visa dropdowns."""
    return {
        city.name: city.country for city in CityRepository(session).list_with_counts()
    }


# Tip categories — key (as stored in the seed data) → display label.
_TIP_CATEGORIES = {
    "transport": "Transport",
    "money": "Money",
    "safety": "Safety",
    "culture": "Culture",
    "food": "Food",
    "connectivity": "Connectivity",
    "health": "Health",
    "etiquette": "Etiquette",
    "best_time": "Best Time",
    "language": "Language",
}


def _flag_emoji(code: str) -> str:
    """Turn an ISO 3166-1 alpha-2 code into its flag emoji, or a white flag if invalid."""
    code = code.strip().upper()
    if len(code) != 2 or not code.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def _tip_destinations(session: Session) -> list[dict]:
    """Country tiles for the picker — name, flag, region, and tip counts.

    Counts come from the country-level seed so the tile number matches the page you land on.
    """
    country_repo = CountryRepository(session)
    tip_repo = TipRepository(session)
    out: list[dict] = []
    for c in country_repo.list():
        tips = tip_repo.for_location("country", c["name"])
        if not tips:
            continue
        out.append(
            {
                "name": c["name"],
                "flag": _flag_emoji(c.get("code", "")),
                "region": c.get("region", "Other"),
                "count": len(tips),
                "essential": sum(1 for t in tips if t.is_essential),
            }
        )
    return out


@router.get("/tips", response_class=HTMLResponse)
def tips_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    country: str | None = Query(None, description="Filter tips by country"),
    city: str | None = Query(None, description="Filter tips by city"),
    category: str | None = Query(None, description="Filter tips by category"),
    essential_only: bool = Query(False, description="Show only must-know tips"),
    browse: str | None = Query(None, description="Set to 'all' to browse every tip"),
) -> HTMLResponse:
    """Render the Local Tips page — picker, destination, or browse view by selection."""
    # The country dropdown lists only countries that have country-level tips, alphabetically.
    destinations = _tip_destinations(session)
    countries = sorted(d["name"] for d in destinations)

    selected_country = country or None
    selected_city = city or None
    # A chosen city drives the country dropdown, regardless of the country submitted.
    if selected_city:
        selected_country = _city_country_map(session).get(
            selected_city, selected_country
        )
    # A chosen country narrows the city dropdown to its cities; otherwise all cities.
    all_cities = CityRepository(session).list_with_counts()
    if selected_country:
        cities = sorted(
            city.name for city in all_cities if city.country == selected_country
        )
    else:
        cities = sorted(city.name for city in all_cities)

    # Coerce an unknown category to "no filter" rather than erroring.
    selected_category = category if category in _TIP_CATEGORIES else None

    if selected_city or selected_country:
        view = "destination"
        result = TipService(session).get_tips(
            city=selected_city,
            country=selected_country,
            category=selected_category,
            essential_only=essential_only,
        )
    elif browse == "all" or selected_category or essential_only:
        # Explicit "browse everything", or a filter applied without a place.
        view = "browse"
        result = TipService(session).get_all_tips(
            category=selected_category,
            essential_only=essential_only,
        )
    else:
        # Nothing chosen → invite the user to pick a destination.
        view = "picker"
        result = None

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="tips.html",
        context={
            "view": view,
            "countries": countries,
            "cities": cities,
            "categories": _TIP_CATEGORIES,
            "selected_country": selected_country,
            "selected_city": selected_city,
            "selected_category": selected_category,
            "essential_only": essential_only,
            "result": result,
            "destinations": destinations,
            "total_tips": sum(d["count"] for d in destinations),
        },
    )


def _visa_destinations(session: Session) -> list[dict]:
    """Country tiles for the visa picker; countries without seeded visa data are skipped."""
    country_repo = CountryRepository(session)
    visa_repo = VisaRepository(session)
    out: list[dict] = []
    for c in country_repo.list():
        visa = visa_repo.get(c["name"])
        if visa is None:
            continue
        out.append(
            {
                "name": c["name"],
                "code": c.get("code", ""),
                "flag": _flag_emoji(c.get("code", "")),
                "region": c.get("region", "Other"),
                "visa_free_days": visa.visa_free_days,
                "visa_on_arrival": visa.visa_on_arrival,
                "e_visa": visa.e_visa,
            }
        )
    return out


@router.get("/visa", response_class=HTMLResponse)
def visa_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    country: str | None = Query(None, description="Filter by country"),
    city: str | None = Query(None, description="Filter by city — resolves its country"),
) -> HTMLResponse:
    """Render the Visa & Entry page — picker or per-country destination view."""
    selected_country = country or None
    selected_city = city or None
    # Visa guidance is country-level, so a city just resolves to its country's card.
    if selected_city:
        selected_country = _city_country_map(session).get(
            selected_city, selected_country
        )

    view = "picker"
    result = None
    flag = ""
    country_code = ""
    if selected_city or selected_country:
        view = "destination"
        result = VisaService(session).get_visa(
            city=selected_city, country=selected_country
        )
        country_code = next(
            (
                c["code"]
                for c in CountryRepository(session).list()
                if c["name"] == result.country
            ),
            "",
        )
        flag = _flag_emoji(country_code)

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="visa.html",
        context={
            "view": view,
            "countries": VisaRepository(session).countries(),
            "selected_country": selected_country,
            "selected_city": selected_city,
            "result": result,
            "flag": flag,
            "country_code": country_code,
            "destinations": _visa_destinations(session),
        },
    )


# Forecast-length dropdown options; 1 = "today only".
_WEATHER_DAYS = [1, 3, 5, 7, 10, 14]


@router.get("/weather", response_class=HTMLResponse)
async def weather_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    city: str | None = Query(None, description="City name to look up"),
    days: int = Query(3, ge=1, le=16, description="Forecast length in days"),
) -> HTMLResponse:
    """Render the live-weather page — a city lookup backed by Open-Meteo.

    An unknown city or upstream failure shows a friendly inline message but still returns HTTP 200.
    """
    suggestions = sorted(
        city.name for city in CityRepository(session).list_with_counts()
    )

    query_city = (city or "").strip()
    weather = None
    error: str | None = None
    if query_city:
        try:
            weather = await weather_service.get_weather(query_city, days=days)
        except CityNotFoundError:
            error = f"Could not find a location named “{query_city}”."
        except WeatherUnavailableError:
            error = "The weather service is unavailable right now — try again shortly."

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="weather.html",
        context={
            "suggestions": suggestions,
            "query_city": query_city,
            "days": days,
            "days_options": _WEATHER_DAYS,
            "weather": weather,
            "error": error,
            "emoji_for_code": weather_service.emoji_for_code,
        },
    )


@router.get("/air-quality", response_class=HTMLResponse)
async def air_quality_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    city: str | None = Query(None, description="City name to look up"),
) -> HTMLResponse:
    """Render the live air-quality page — a city lookup backed by Open-Meteo.

    An unknown city or upstream failure shows a friendly inline message but still returns HTTP 200.
    """
    suggestions = sorted(
        city.name for city in CityRepository(session).list_with_counts()
    )

    query_city = (city or "").strip()
    air_quality = None
    error: str | None = None
    if query_city:
        try:
            air_quality = await air_quality_service.get_air_quality(query_city)
        except CityNotFoundError:
            error = f"Could not find a location named “{query_city}”."
        except WeatherUnavailableError:
            error = (
                "The air-quality service is unavailable right now — try again shortly."
            )

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="air_quality.html",
        context={
            "suggestions": suggestions,
            "query_city": query_city,
            "air_quality": air_quality,
            "error": error,
        },
    )


@router.get("/bookings", response_class=HTMLResponse)
def bookings_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    q: str | None = Query(None, description="Search booking ID, customer name, email"),
    booking_type: str | None = Query(None, alias="type", description="Filter by type"),
    sort: str = Query("created_desc", description="Sort order; see BOOKING_SORTS keys"),
) -> HTMLResponse:
    """Render the read-only bookings ledger — every flight and hotel booking made."""
    service = BookingService(session)
    # Operator dashboard (Basic-auth, no signed-in caller): the one place that reads
    # the unscoped ledger across all owners.
    bookings = service.query_unscoped(q=q, booking_type=booking_type, sort=sort)
    selected_type = booking_type if booking_type in ("flight", "hotel") else None
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="bookings.html",
        context={
            "bookings": bookings,
            "total": len(service.list_all_unscoped()),
            "query": (q or "").strip(),
            "selected_type": selected_type,
            "sort": sort if sort in BOOKING_SORTS else "created_desc",
        },
    )


def _model_hints() -> list[str]:
    """Union of catalog models across providers — datalist hints, not an allowlist."""
    return sorted({m for p in LLM_PROVIDERS.values() for m in p.models})


def _render_agent_config_edit(
    request: Request,
    *,
    agent_name: str,
    provider: str,
    model: str,
    temperature: str,
    max_tokens: str,
    updated_at: str | None = None,
    error: str | None = None,
    status_code: int = 200,
    enabled: bool | None = None,
) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="agent_config_edit.html",
        context={
            "agent_name": agent_name,
            "provider_value": provider,
            "model_value": model,
            "temperature_value": temperature,
            "max_tokens_value": max_tokens,
            "updated_at": updated_at,
            "error": error,
            "providers": sorted(PROVIDER_NAMES),
            "model_hints": _model_hints(),
            "enabled_value": enabled,
        },
        status_code=status_code,
    )


@router.get("/agent-config", response_class=HTMLResponse)
def agent_config_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """List every agent's LLM config, grouped into sections (edit in a modal)."""
    groups = AgentConfigService(session).list_grouped()
    # Re-check on render so a hand-crafted link cannot show a banner for a priced model.
    unpriced_model = request.query_params.get("unpriced_model", "").strip()
    unpriced = (
        {
            "agent": request.query_params.get("unpriced_agent", ""),
            "model": unpriced_model,
        }
        if unpriced_model and not is_priced(unpriced_model)
        else None
    )
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="agent_config.html",
        context={
            "groups": groups,
            "unpriced": unpriced,
            "providers": sorted(PROVIDER_NAMES),
            "provider_models": {
                name: list(p.models) for name, p in LLM_PROVIDERS.items()
            },
        },
    )


@router.get("/agent-config/{agent_name}", response_class=HTMLResponse)
def agent_config_edit_page(
    request: Request,
    agent_name: str,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """Render the edit form for one agent (404 if unknown)."""
    v = AgentConfigService(session).get_config(agent_name)  # NotFoundError → 404
    return _render_agent_config_edit(
        request,
        agent_name=v.agent_name,
        provider=v.provider or "",
        model=v.model or "",
        temperature="" if v.temperature is None else str(v.temperature),
        max_tokens="" if v.max_tokens is None else str(v.max_tokens),
        updated_at=v.updated_at,
        enabled=v.enabled,
    )


@router.post("/agent-config/{agent_name}", response_class=HTMLResponse)
def agent_config_save(
    request: Request,
    agent_name: str,
    session: Annotated[Session, Depends(get_session)],
    provider: str = Form(""),
    model: str = Form(""),
    temperature: str = Form(""),
    max_tokens: str = Form(""),
    enabled: str | None = Form(None),
    enabled_marker: str | None = Form(None),
) -> Response:
    """Persist one agent's config, then redirect back (PRG). Invalid input → 400 + form."""
    svc = AgentConfigService(session)
    svc.get_config(agent_name)  # 404 before any write if the agent is unknown
    # No marker → this form doesn't own the flag → preserve it (None = don't touch).
    # Marker present → an unchecked checkbox submits nothing, so `enabled` is None.
    enabled_val = None if enabled_marker is None else (enabled == "on")
    try:
        svc.update_config(
            agent_name,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            enabled=enabled_val,
        )
    except DomainValidationError as exc:
        return _render_agent_config_edit(
            request,
            agent_name=agent_name,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            error=str(exc),
            status_code=400,
            enabled=enabled_val,
        )
    # PRG back to the list page, where the "saved" confirmation banner lives.
    params = {"saved": 1}
    saved_model = model.strip()  # what the service persists (blank → default)
    if saved_model and not is_priced(saved_model):
        # Non-blocking: the save stands; the list page warns that cost will be NULL.
        params |= {"unpriced_agent": agent_name, "unpriced_model": saved_model}
    return RedirectResponse(
        url=f"/dashboard/agent-config?{urlencode(params)}", status_code=303
    )


def _percentile(values: list[int], pct: float) -> int | None:
    """Nearest-rank percentile of *values* (empty yields ``None``)."""
    if not values:
        return None
    ordered = sorted(values)
    # Nearest-rank: index = ceil(pct/100 * n) - 1, clamped to the last element.
    idx = min(len(ordered) - 1, max(0, ceil(pct / 100 * len(ordered)) - 1))
    return ordered[idx]


def _run_totals(repo: AgentRunRepository, since: datetime) -> dict:
    """Aggregate metrics since *since*, with p50 / p95 latency added."""
    t = repo.totals(since)
    latencies = t["latencies"]
    return {
        "turns": t["turns"],
        "tokens": t["tokens"],
        "cost": t["cost"],
        "p50": _percentile(latencies, 50),
        "p95": _percentile(latencies, 95),
    }


@router.get("/agent-runs", response_class=HTMLResponse)
def agent_runs_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """Render the recent agent-turn metrics and 24h / 7d rollups.

    Read-only operator view; a ``running`` row older than ten minutes is treated as abandoned.
    """
    repo = AgentRunRepository(session)
    runs = repo.list_recent(100)
    now = datetime.now(UTC)
    totals_24h = _run_totals(repo, now - timedelta(hours=24))
    totals_7d = _run_totals(repo, now - timedelta(days=7))
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="agent_runs.html",
        context={
            "runs": runs,
            "totals_24h": totals_24h,
            "totals_7d": totals_7d,
            # Rows started before this cutoff and still "running" are abandoned.
            "abandoned_cutoff": (now - timedelta(minutes=10)).isoformat(),
        },
    )


#: Minimum bar width (%) so a 0 ms step is still visible in the waterfall.
_MIN_BAR_PCT = 0.8


def _attributed_prompt_names(steps: list) -> set[str]:
    """Prompt names the run's steps could be attributed to.

    Steps that compose no registry prompt (``tools``, ``trip_guard``,
    ``synthesize`` / ``summarize``) stay unattributed.
    """
    names: set[str] = set()
    for step in steps:
        for entry in step.prompts or []:
            name = entry.get("name") if isinstance(entry, dict) else None
            if name:
                names.add(name)
    return names


def _turn_span_ms(run: models.AgentRun, steps: list[models.AgentRunStep]) -> int:
    """Wall-clock span the waterfall is drawn against.

    ``latency_ms`` if recorded, else the furthest step end, else 0 — the caller
    must not divide by a 0 span.
    """
    if run.latency_ms:
        return run.latency_ms
    if steps:
        return max((s.offset_ms or 0) + (s.ms or 0) for s in steps)
    return 0


def _waterfall(run: models.AgentRun, steps: list[models.AgentRunStep]) -> list[dict]:
    """Position each step's bar as percentages of the turn span.

    All arithmetic happens here so the template only prints numbers; a zero span
    yields left-aligned minimum-width bars rather than a division by zero.
    """
    span = _turn_span_ms(run, steps)
    rows: list[dict] = []
    for step in steps:
        if span > 0:
            left = (step.offset_ms or 0) / span * 100
            width = (step.ms or 0) / span * 100
        else:
            left, width = 0.0, 0.0
        # Clamp so a bar always stays inside the track and stays visible.
        left = min(max(left, 0.0), 100.0 - _MIN_BAR_PCT)
        width = min(max(width, _MIN_BAR_PCT), 100.0 - left)
        ns = step.ns or ""
        rows.append(
            {
                "step": step,
                "left_pct": round(left, 2),
                "width_pct": round(width, 2),
                # A '|' in the checkpoint ns means the node ran in a sub-graph, named by its root.
                "sub": ns.split("|", 1)[0].split(":", 1)[0] if "|" in ns else None,
            }
        )
    return rows


def _cost_by_model(
    run: models.AgentRun, steps: list[models.AgentRunStep]
) -> list[dict]:
    """Per-model usage from ``by_model``, with cost summed from that model's LLM steps."""
    costs: dict[str, float] = {}
    for step in steps:
        if step.model and step.cost_usd is not None:
            costs[step.model] = costs.get(step.model, 0.0) + step.cost_usd
    rows = []
    for model, usage in sorted((run.by_model or {}).items()):
        rows.append(
            {
                "model": model,
                "calls": usage.get("calls", 0),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cached_tokens": usage.get("cached_tokens", 0),
                "cost_usd": costs.get(model),
            }
        )
    return rows


@router.get("/agent-runs/{run_id}", response_class=HTMLResponse)
def agent_run_detail_page(
    request: Request,
    run_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """Render one turn's call chain as a waterfall (read-only operator view)."""
    run = session.get(models.AgentRun, run_id)
    if run is None:
        raise NotFoundError(f"No agent run with id {run_id!r}")
    steps = AgentRunRepository(session).steps_for(run_id)
    attributed = _attributed_prompt_names(steps)
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="agent_run_detail.html",
        context={
            "run": run,
            "chain": _waterfall(run, steps),
            "span_ms": _turn_span_ms(run, steps),
            "by_model": _cost_by_model(run, steps),
            "tools": [s for s in steps if s.kind == "tool"],
            # Every prompt the compiled graph had active (not only this turn's); the
            # third flag marks the subset steps could attribute — unflagged ≠ unused.
            "prompts": [
                (name, version, name in attributed)
                for name, version in sorted((run.prompt_versions or {}).items())
            ],
            # Recording stops past MAX_STEPS_PER_TURN and that counter isn't persisted,
            # so a full page of steps is the only signal the chain may be incomplete.
            "truncated": len(steps) >= _MAX_STEPS_PER_TURN,
        },
    )


def _today() -> str:
    """Today's date as a YYYY-MM-DD string (the board's default date)."""
    return date.today().isoformat()
