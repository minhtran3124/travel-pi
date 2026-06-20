"""Server-rendered dashboard pages (HTML), separate from the JSON API.

These routes return HTML built with Jinja2 templates — they are for humans
with a browser, not for the FE's TypeScript client. They are excluded from
the OpenAPI schema (``include_in_schema=False``) so they never show up in
``/docs`` or the generated TS types.

Pages:
    GET /dashboard/flights              airport-style arrivals/departures board
    GET /dashboard/flights/search       optional lookup by exact route
    GET /dashboard/flights/{flight_id}  single-flight detail page
    GET /dashboard/hotels               browsable card grid of all hotels
    GET /dashboard/places               browsable grid of attractions
    GET /dashboard/tips                 local tips by country / city
    GET /dashboard/weather              live city weather lookup (Open-Meteo)
    GET /dashboard/air-quality          live city air-quality lookup (Open-Meteo)
    GET /dashboard/bookings             ledger of every flight/hotel booking
"""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.params import parse_optional_number
from app.crud.airline import AIRLINE_COLOR_DEFAULT, AirlineRepository
from app.crud.city import CityRepository
from app.crud.country import CountryRepository
from app.crud.tip import TipRepository
from app.crud.visa import VisaRepository
from app.db.session import get_session
from app.exceptions import CityNotFoundError, WeatherUnavailableError
from app.services import (
    air_quality_service,
    board_service,
    flight_service,
    weather_service,
)
from app.services.airport_service import AirportService
from app.services.board_service import BoardService
from app.services.booking_service import BOOKING_SORTS, BookingService
from app.services.flight_service import FlightService
from app.services.hotel_service import HotelService
from app.services.place_service import PlaceService
from app.services.tip_service import TipService
from app.services.visa_service import VisaService

router = APIRouter(prefix="/dashboard", tags=["dashboard"], include_in_schema=False)

# Templates live in app/templates/ — resolve the path relative to this file
# so it works regardless of the current working directory.
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Custom filter: 221 -> "3h41m". Used in the duration columns.
_TEMPLATES.env.filters["hm"] = lambda minutes: f"{minutes // 60}h{minutes % 60:02d}m"

# The board defaults to this airport when none is given (busiest hub).
_DEFAULT_AIRPORT = "SGN"


@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard_index(request: Request) -> HTMLResponse:
    """Render the dashboard landing page.

    A standalone intro to the Travel Planner that walks through the itinerary
    flow — Flights → Hotels → Places → Local Tips → Weather — as an animated
    sequence, with each step linking to its section. Replaces the old redirect
    straight to the flights board.
    """
    return _TEMPLATES.TemplateResponse(request=request, name="index.html")


@router.get("/checklist", response_class=HTMLResponse)
def checklist_page(request: Request) -> HTMLResponse:
    """Render the personal travel checklist.

    Pure client-side: trips and saved places live in the browser
    (localStorage), so there is no backend state or context to pass.
    """
    return _TEMPLATES.TemplateResponse(request=request, name="checklist.html")


@router.get("/_search.json", include_in_schema=False)
def palette_index(
    session: Annotated[Session, Depends(get_session)],
) -> JSONResponse:
    """Lightweight index for the command palette (cities + airports).

    Fetched once, client-side, the first time the palette opens.
    """
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
    """Render the main flight board for one airport and date.

    This is the primary page — an airport-style FIDS board. ``airport``,
    ``date``, and ``mode`` are an optional filter; with no params it shows
    today's arrivals for the default hub.
    """
    airports_svc = AirportService(session)
    if mode not in (board_service.ARRIVALS, board_service.DEPARTURES):
        mode = board_service.ARRIVALS
    # Resolve the board's airport, falling back to the default for unknown codes.
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

    With no query params it shows just the empty form. Once origin,
    destination, and date are all provided it renders the matching flights,
    with the same airline / price / stops filters and sort as the JSON API.

    The numeric filters arrive as raw strings because an HTML form submits
    empty fields as ``""`` — those are treated as "not filtered", and a
    non-numeric value shows a friendly error rather than a 422.
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

    If the ID does not resolve, the template shows a friendly "not found"
    message (the page itself still returns HTTP 200 — it is a valid page).
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
) -> HTMLResponse:
    """Render the browsable hotel grid.

    With no params it shows every seeded hotel. ``city`` narrows the grid to
    one city (case-insensitive exact match), ``q`` keeps only hotels whose
    name contains the query, and ``sort`` reorders the result. Filters that
    match nothing yield an empty grid rather than an error, mirroring the
    JSON API's behaviour.
    """
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

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="hotels.html",
        context={
            "hotels": hotels,
            "cities": cities,
            "selected_city": selected_city,
            "query": query,
            "sort": sort,
            "total": len(all_hotels),
        },
    )


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
) -> HTMLResponse:
    """Render the browsable places/attractions grid.

    ``min_rating`` and ``price_level`` are accepted as strings so that an
    empty string from the HTML form (when "Any" is selected) maps cleanly to
    ``None`` rather than raising a 422 validation error.
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

    # Skip the search on bad input so the page renders the error and the
    # picker, not a misleading "everything" list.
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

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="places.html",
        context={
            "places": results,
            "total": len(all_places),
            "cities": cities,
            "categories": _PLACE_CATEGORIES,
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


def _city_country_map(session: Session) -> dict[str, str]:
    """City → country map, used to link the Local Tips / Visa dropdowns.

    Built per call from the DB-backed city repo (cheap; the dataset is small).
    """
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
    """Turn an ISO 3166-1 alpha-2 code into its flag emoji (VN → 🇻🇳)."""
    code = code.strip().upper()
    if len(code) != 2 or not code.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def _tip_destinations(session: Session) -> list[dict]:
    """Country tiles for the picker — name, flag, region, and tip counts.

    Counts come straight from the country-level seed (what a country view
    shows), so the tile number matches the page you land on.
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
    """Render the Local Tips page — curated destination advice.

    Three views, chosen by what's selected:
    - **picker** (default, nothing selected): a friendly grid of destinations.
    - **destination** (``country`` or ``city``): that place's field guide,
      essentials first. A city wins and resolves its own country.
    - **browse** (``browse=all``, or a category / essential-only filter with
      no destination): every tip merged, grouped by category.

    Country and city options come from the same seed data as the JSON API.
    """
    # Country tiles (name/flag/region/counts) for the picker; the country
    # dropdown lists the same countries (those that have country-level tips),
    # alphabetically — mirrors the old ``sorted(COUNTRY_TIPS)``.
    destinations = _tip_destinations(session)
    countries = sorted(d["name"] for d in destinations)

    selected_country = country or None
    selected_city = city or None
    # Reverse linkage: a chosen city drives the country dropdown — the
    # country follows the city, regardless of what country was submitted.
    if selected_city:
        selected_country = _city_country_map(session).get(
            selected_city, selected_country
        )
    # Forward linkage: with a country chosen, the city dropdown lists only
    # that country's cities; otherwise it lists every city.
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
    """Country tiles for the visa picker — flag, region, and at-a-glance facts.

    Walks ``countries.py`` (the canonical, region-ordered list) and pulls each
    country's entry guidance from ``COUNTRY_VISA``; countries without seeded
    visa data are skipped so a tile always links to a populated page.
    """
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
    """Render the Visa & Entry page — general entry-requirement guidance.

    Two views, chosen by what's selected:
    - **picker** (default, nothing selected): country tiles grouped by region.
    - **destination** (``country`` or ``city``): that country's entry card. A
      city wins and resolves its own country, mirroring the JSON ``/visa`` API.

    Guidance is general and nationality-dependent — every entry card carries
    the API's ``disclaimer``.
    """
    selected_country = country or None
    selected_city = city or None
    # Visa guidance is country-level, so a city (from a cross-link or the
    # palette) just resolves to its country's card — there's no city filter.
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


# Forecast-length options offered in the weather page dropdown.
# 1 = "today only", the rest are multi-day forecasts.
_WEATHER_DAYS = [1, 3, 5, 7, 10, 14]


@router.get("/weather", response_class=HTMLResponse)
async def weather_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    city: str | None = Query(None, description="City name to look up"),
    days: int = Query(3, ge=1, le=16, description="Forecast length in days"),
) -> HTMLResponse:
    """Render the live-weather page — a city lookup backed by Open-Meteo.

    With no ``city`` it shows just the search form. Once a city is given it
    fetches current conditions plus a ``days``-long forecast; an unknown city
    or an upstream failure is shown as a friendly inline message (the page
    itself still returns HTTP 200).
    """
    # Suggested cities for the input's autocomplete — sourced from the same
    # canonical city list that backs the /cities API (app/data/cities.py).
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

    With no ``city`` it shows just the search form. Once a city is given it
    fetches the current US-AQI, the six pollutants, and a short per-day max-AQI
    forecast; an unknown city or an upstream failure is shown as a friendly
    inline message (the page itself still returns HTTP 200).
    """
    # Same canonical city list the /cities API uses — drives the dropdown.
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
    """Render the bookings ledger — every flight and hotel booking made.

    Bookings are the only persisted state (SQLite). This page is read-only;
    ``q``, ``type``, and ``sort`` search, filter, and reorder the ledger.
    """
    service = BookingService(session)
    bookings = service.query(q=q, booking_type=booking_type, sort=sort)
    selected_type = booking_type if booking_type in ("flight", "hotel") else None
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="bookings.html",
        context={
            "bookings": bookings,
            "total": len(service.list_all()),
            "query": (q or "").strip(),
            "selected_type": selected_type,
            "sort": sort if sort in BOOKING_SORTS else "created_desc",
        },
    )


def _today() -> str:
    """Today's date as a YYYY-MM-DD string (the board's default date)."""
    return date.today().isoformat()
