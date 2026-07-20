"""Climate (monthly-normals) tool (specs/weather-trip-date-accuracy Task 1.2).

``get_climate`` wraps the existing ``climate_service.get_climate`` so the agent
can answer questions about dates too far out for a day-by-day forecast. It is
deliberately NOT a forecast: it returns averages computed over several years
of historical data, not a prediction for specific days. See ``get_weather`` /
``get_packing`` in ``weather_tools.py`` for the forecast-horizon tools this
one complements.
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import Field

from app.exceptions import AppError, UpstreamError
from app.schemas.base import AppBaseModel
from app.services import climate_service
from app.tools._base import dump, log_tool_call, tool_error


class GetClimateArgs(AppBaseModel):
    city: str = Field(..., description="The city to get climate normals for.")
    month: int | None = Field(
        None,
        description=(
            "Optional month number (1=January .. 12=December) to filter the "
            "normals to. Omit to get all 12 months."
        ),
    )


@tool(args_schema=GetClimateArgs)
async def get_climate(city: str, month: int | None = None) -> dict:
    """Get typical/average monthly weather conditions (climate normals) for a city.

    This returns MONTHLY NORMALS averaged over several years of historical
    data — typical temperature range, rainfall, and rainy-day counts for each
    calendar month — NOT a forecast for specific days. Use this tool when a
    trip date is beyond the forecast horizon (too far in the future for
    ``get_weather``/``get_packing`` to cover). Describe the result as
    "typical" or "average" conditions for that time of year, never as a
    forecast for the exact dates.

    :param city: The city to get climate normals for.
    :param month: Optional month number (1-12) to filter the normals to.
    :return: The monthly climate normals, filtered to ``month`` when given.
    """
    log_tool_call("get_climate", locals())
    try:
        return dump(await climate_service.get_climate(city, month))
    except UpstreamError:
        raise  # transient — let RetryPolicy retry the node
    except AppError as e:
        raise tool_error(e) from e


CLIMATE_TOOLS = [get_climate]
