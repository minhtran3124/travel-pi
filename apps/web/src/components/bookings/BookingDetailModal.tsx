"use client";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Pill } from "@/components/ui/Pill";
import { Spinner } from "@/components/ui/Spinner";
import type { Booking } from "@/lib/query/bookings";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-md py-xs">
      <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
        {label}
      </span>
      <span className="text-right text-sm text-ink">{value}</span>
    </div>
  );
}

function FlightDetails({ booking }: { booking: Booking }) {
  const d = booking.details;
  if (d.kind !== "flight") return null;
  return (
    <div className="flex flex-col">
      <Row label="Flight" value={`${d.airline} ${d.flight_number}`} />
      <Row label="Route" value={`${d.origin} → ${d.destination}`} />
      <Row label="Departs" value={d.departure_time} />
      <Row label="Arrives" value={d.arrival_time} />
      <Row label="Passenger" value={d.passenger_name} />
      {d.passenger_phone ? (
        <Row label="Phone" value={d.passenger_phone} />
      ) : null}
    </div>
  );
}

function HotelDetails({ booking }: { booking: Booking }) {
  const d = booking.details;
  if (d.kind !== "hotel") return null;
  return (
    <div className="flex flex-col">
      <Row label="Hotel" value={d.hotel_name} />
      <Row label="City" value={d.city} />
      <Row label="Check-in" value={d.check_in} />
      <Row label="Check-out" value={d.check_out} />
      <Row label="Nights" value={String(d.nights)} />
      <Row label="Rooms" value={String(d.rooms)} />
      <Row label="Guests" value={`${d.adults} adults, ${d.children} children`} />
      {d.guest_phone ? <Row label="Phone" value={d.guest_phone} /> : null}
    </div>
  );
}

export interface BookingDetailModalProps {
  booking: Booking | null;
  open: boolean;
  onClose: () => void;
  onCancel: (id: string) => void;
  cancelling?: boolean;
}

export function BookingDetailModal({
  booking,
  open,
  onClose,
  onCancel,
  cancelling = false,
}: BookingDetailModalProps) {
  if (!booking) return null;

  const isCancelled = booking.status === "cancelled";
  const price = booking.total_price.toLocaleString(undefined, {
    style: "currency",
    currency: booking.currency,
  });

  return (
    <Modal open={open} onClose={onClose} title={booking.summary}>
      <div className="flex flex-col gap-md">
        <div className="flex flex-wrap items-center gap-sm">
          <Pill
            variant={booking.type === "hotel" ? "status" : "topic"}
            tone={booking.type === "hotel" ? "hotel" : "transport"}
            label={booking.type === "hotel" ? "Hotel" : "Flight"}
          />
          <Pill
            variant="status"
            tone={isCancelled ? "cancelled" : "confirmed"}
            label={isCancelled ? "Cancelled" : "Confirmed"}
          />
        </div>

        <div className="flex items-baseline justify-between gap-md">
          <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
            Confirmation
          </span>
          <span className="font-mono text-sm text-ink">
            {booking.confirmation_code}
          </span>
        </div>

        <div className="rounded-sm border border-line-soft bg-panel p-md">
          {booking.details.kind === "flight" ? (
            <FlightDetails booking={booking} />
          ) : (
            <HotelDetails booking={booking} />
          )}
        </div>

        <div className="flex flex-col">
          <Row label="Customer" value={booking.customer_name} />
          <Row label="Email" value={booking.customer_email} />
          <div className="flex items-baseline justify-between gap-md py-xs">
            <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
              Total
            </span>
            <span className="text-right text-sm font-bold text-ink tabular-nums">
              {price}
            </span>
          </div>
        </div>

        <div className="flex justify-end gap-sm">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {!isCancelled ? (
            <Button
              variant="primary"
              onClick={() => onCancel(booking.id)}
              disabled={cancelling}
            >
              {cancelling ? <Spinner label="Cancelling" /> : "Cancel booking"}
            </Button>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
