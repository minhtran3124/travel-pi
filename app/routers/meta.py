"""Meta endpoint: service info."""

from fastapi import APIRouter

from app.schemas.meta import ServiceInfo

router = APIRouter(tags=["meta"])


@router.get("/", response_model=ServiceInfo, summary="Service info")
def root() -> ServiceInfo:
    """Return the service name, docs URL, and available endpoint paths."""
    return ServiceInfo(
        name="Travel Planner Mock API",
        docs="/docs",
        endpoints=[
            "GET /airports",
            "GET /flights/search",
            "GET /flights/{flight_id}",
            "POST /flights/book",
            "GET /hotels/search",
            "GET /hotels/{hotel_id}",
            "POST /hotels/book",
            "GET /places/search",
            "GET /tips",
            "GET /weather",
            "GET /bookings/{booking_id}",
        ],
    )
