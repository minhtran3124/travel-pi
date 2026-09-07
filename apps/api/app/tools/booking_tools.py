"""Booking lifecycle tools — cancel a flight or hotel booking (MIN-42).

Thin wrappers over ``BookingService.cancel``. Cancellation is irreversible, so
each tool requires ``confirm=True`` and is annotated destructive in the registry.
Two type-specific tools (not one generic) give an explicit MCP surface; each
loads the booking first via ``BookingService.get`` and refuses a booking of the
other type. Mirrors the ``book_hotel`` error-mapping pattern.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from app.enums import BookingType
from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.services.booking_service import BookingService
from app.tools._base import dump, log_tool_call, session_scope, tool_error


class CancelBookingArgs(AppBaseModel):
    booking_id: str = Field(
        ...,
        description=(
            "The booking UUID or 6-character confirmation code (e.g. 'AB23XY') "
            "of the booking to cancel."
        ),
    )
    confirm: bool = Field(
        False,
        description=(
            "Must be set to True to execute the cancellation — this cannot be "
            "undone. Leaving it False (the default) cancels nothing."
        ),
    )
    user_id: Annotated[str, InjectedState("user_id")] = Field(
        default="",
        description="Injected owner id from graph state — never supplied by the model.",
    )


def _cancel(
    booking_id: str,
    confirm: bool,
    expected: BookingType,
    tool_name: str,
    user_id: str,
) -> dict:
    """Shared cancel path: guard confirm → load → type-check → cancel → dump.

    ``user_id`` scopes both the load and the cancel to the caller: a booking
    owned by someone else resolves to the same not-found error as one that does
    not exist (#118), so a foreign booking can never be cancelled.
    """
    log_tool_call(tool_name, {"booking_id": booking_id, "confirm": confirm})
    if not confirm:
        raise ToolException(
            "set confirm=true to cancel — this permanently cancels the booking"
        )
    with session_scope() as s:
        try:
            svc = BookingService(s)
            booking = svc.get(booking_id, user_id=user_id)
            if booking.type != expected:
                raise ToolException(
                    f"Booking {booking_id!r} is a {booking.type.value} booking, "
                    f"not a {expected.value} booking. "
                    f"Use cancel_{booking.type.value} instead."
                )
            return dump(svc.cancel(booking_id, user_id=user_id))
        except AppError as e:
            raise tool_error(e) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


@tool(args_schema=CancelBookingArgs)
def cancel_flight(
    booking_id: str,
    confirm: bool = False,
    user_id: Annotated[str, InjectedState("user_id")] = "",
) -> dict:
    """Cancel a FLIGHT booking. You MUST pass confirm=True — this cannot be undone.

    Raises ``ToolException`` if the id is unknown or refers to a hotel booking.
    Cancelling an already-cancelled booking is a no-op that returns it.

    :param booking_id: Booking UUID or 6-char confirmation code.
    :param confirm: Must be True to execute the cancellation.
    :param user_id: The owner id, injected from graph state (not model-supplied);
        a booking owned by someone else reads as not found.
    :return: The cancelled Booking (status='cancelled').
    """
    return _cancel(
        booking_id, confirm, BookingType.FLIGHT, "cancel_flight", user_id=user_id
    )


@tool(args_schema=CancelBookingArgs)
def cancel_hotel(
    booking_id: str,
    confirm: bool = False,
    user_id: Annotated[str, InjectedState("user_id")] = "",
) -> dict:
    """Cancel a HOTEL booking. You MUST pass confirm=True — this cannot be undone.

    Raises ``ToolException`` if the id is unknown or refers to a flight booking.
    Cancelling an already-cancelled booking is a no-op that returns it.

    :param booking_id: Booking UUID or 6-char confirmation code.
    :param confirm: Must be True to execute the cancellation.
    :param user_id: The owner id, injected from graph state (not model-supplied);
        a booking owned by someone else reads as not found.
    :return: The cancelled Booking (status='cancelled').
    """
    return _cancel(
        booking_id, confirm, BookingType.HOTEL, "cancel_hotel", user_id=user_id
    )


BOOKING_TOOLS = [cancel_flight, cancel_hotel]
