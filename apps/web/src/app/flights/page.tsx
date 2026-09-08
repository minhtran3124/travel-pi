"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { UpgradeDialog } from "@/components/booking/UpgradeDialog";
import { FlightResultCard } from "@/components/flights/FlightResultCard";
import { PanelIntlProvider } from "@/components/chat/panel/PanelIntlProvider";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { useTrips } from "@/lib/query/trips";
import {
  PremiumRequiredError,
  useBookFlight,
  useFlightSearch,
  type Booking,
  type Flight,
  type FlightSearchFilters,
} from "@/lib/query/flights";
import type { FlightsPanelFlight } from "@/lib/stream/panel";

const EMPTY_FILTERS: FlightSearchFilters = {
  origin: "",
  destination: "",
  departure_date: "",
};

/** `Flight` (from /flights/search) → the flat shape `FlightResultCard` renders. */
function toPanelFlight(f: Flight): FlightsPanelFlight {
  return {
    id: f.id,
    flight_number: f.flight_number,
    airline_name: f.airline.name,
    airline_code: f.airline.code,
    origin: f.origin,
    destination: f.destination,
    departure_time: f.departure_time,
    arrival_time: f.arrival_time,
    duration_minutes: f.duration_minutes,
    stops: f.stops,
    seats_available: f.seats_available,
    price: f.price,
    currency: f.currency,
  };
}

const EMPTY_BOOK_FORM = { name: "", email: "", phone: "" };

export default function FlightsPage() {
  const t = useTranslations("Flights");
  const locale = useLocale();
  const searchParams = useSearchParams();
  const prefilledTripId = searchParams.get("tripId") ?? "";

  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [departureDate, setDepartureDate] = useState("");
  const [returnDate, setReturnDate] = useState("");
  const [adults, setAdults] = useState("1");
  const [submitted, setSubmitted] = useState<FlightSearchFilters | null>(null);

  const { data, isLoading, isError } = useFlightSearch(
    submitted ?? EMPTY_FILTERS,
    submitted !== null,
  );
  const results = data?.results ?? [];
  const cheapestPrice = results.length
    ? Math.min(...results.map((f) => f.price))
    : null;

  // The whole list, not the default first page of 20: the derivation below
  // treats an id that is absent from `trips` as "no trip", so a short page
  // would silently drop a valid ?tripId= for anyone with more than 20 trips.
  // 500 is the server's maximum page size.
  const { data: tripsData } = useTrips({ limit: 500 });
  const trips = tripsData?.results ?? [];

  const [bookTarget, setBookTarget] = useState<Flight | null>(null);
  const [bookForm, setBookForm] = useState(EMPTY_BOOK_FORM);
  const [selectedTripId, setSelectedTripId] = useState("");

  // A `?tripId=` link can point at a trip that's since been deleted, or one
  // the current user doesn't own. Derive the selection during render rather
  // than correcting it in an effect: until trips load we trust the id, and
  // once they have, an id that isn't among them reads as "no trip" — which
  // is what the select shows and what the form submits.
  const tripId =
    selectedTripId &&
    (tripsData === undefined ||
      trips.some((trip) => trip.id === selectedTripId))
      ? selectedTripId
      : "";
  const [bookResult, setBookResult] = useState<Booking | null>(null);
  const [bookError, setBookError] = useState<string | null>(null);
  const bookFlight = useBookFlight();

  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [upgradeHint, setUpgradeHint] = useState<string | undefined>(undefined);

  function search(e: React.FormEvent) {
    e.preventDefault();
    if (!origin.trim() || !destination.trim() || !departureDate) return;
    const parsedAdults = Number.parseInt(adults, 10);
    setSubmitted({
      origin: origin.trim().toUpperCase(),
      destination: destination.trim().toUpperCase(),
      departure_date: departureDate,
      ...(returnDate ? { return_date: returnDate } : {}),
      adults: Number.isNaN(parsedAdults) ? 1 : Math.max(1, parsedAdults),
    });
  }

  function openBook(flight: Flight) {
    setBookTarget(flight);
    setBookForm(EMPTY_BOOK_FORM);
    setSelectedTripId(prefilledTripId);
    setBookResult(null);
    setBookError(null);
  }

  function closeBook() {
    setBookTarget(null);
    setBookForm(EMPTY_BOOK_FORM);
    setBookResult(null);
    setBookError(null);
    bookFlight.reset();
  }

  async function submitBook(e: React.FormEvent) {
    e.preventDefault();
    if (!bookTarget) return;
    setBookError(null);
    try {
      const booking = await bookFlight.mutateAsync({
        flight_id: bookTarget.id,
        passenger_name: bookForm.name.trim(),
        passenger_email: bookForm.email.trim(),
        passenger_phone: bookForm.phone.trim(),
        trip_id: tripId || undefined,
      });
      setBookResult(booking);
    } catch (err) {
      if (err instanceof PremiumRequiredError) {
        setUpgradeHint(err.hint);
        setUpgradeOpen(true);
        setBookTarget(null);
        return;
      }
      setBookError(t("bookError"));
    }
  }

  return (
    <div className="flex flex-col gap-lg">
      <h1 className="text-[1.35rem] font-extrabold text-ink">{t("title")}</h1>

      <form
        onSubmit={search}
        className="flex flex-wrap items-end gap-md rounded-md border border-line bg-panel p-md"
      >
        <Field
          label={t("originLabel")}
          placeholder={t("originPlaceholder")}
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
          wrapperClassName="min-w-[8rem]"
        />
        <Field
          label={t("destinationLabel")}
          placeholder={t("destinationPlaceholder")}
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          wrapperClassName="min-w-[8rem]"
        />
        <Field
          label={t("departureDateLabel")}
          type="date"
          value={departureDate}
          onChange={(e) => setDepartureDate(e.target.value)}
          wrapperClassName="min-w-[10rem]"
        />
        <Field
          label={t("returnDateLabel")}
          type="date"
          value={returnDate}
          onChange={(e) => setReturnDate(e.target.value)}
          wrapperClassName="min-w-[10rem]"
        />
        <Field
          label={t("adultsLabel")}
          type="number"
          min={1}
          value={adults}
          onChange={(e) => setAdults(e.target.value)}
          wrapperClassName="w-24"
        />
        <Button
          type="submit"
          disabled={!origin.trim() || !destination.trim() || !departureDate}
        >
          {t("searchButton")}
        </Button>
      </form>

      {submitted === null ? (
        <EmptyState icon="✈️" title={t("promptTitle")} hint={t("promptHint")} />
      ) : isLoading ? (
        <div className="flex justify-center py-xl">
          <Spinner label={t("loadingLabel")} />
        </div>
      ) : isError ? (
        <EmptyState icon="⚠️" title={t("errorTitle")} hint={t("errorHint")} />
      ) : results.length === 0 ? (
        <EmptyState icon="✈️" title={t("emptyTitle")} hint={t("emptyHint")} />
      ) : (
        <PanelIntlProvider language={locale}>
          <div className="flex flex-col gap-sm">
            {results.map((f) => (
              <div key={f.id} className="flex items-center gap-sm">
                <div className="flex-1">
                  <FlightResultCard
                    f={toPanelFlight(f)}
                    cheapest={f.price === cheapestPrice}
                  />
                </div>
                <Button onClick={() => openBook(f)}>{t("bookButton")}</Button>
              </div>
            ))}
          </div>
        </PanelIntlProvider>
      )}

      <Modal
        open={bookTarget !== null}
        onClose={closeBook}
        title={bookResult ? t("successTitle") : t("bookModalTitle")}
      >
        {bookResult ? (
          <div className="flex flex-col gap-md">
            <p className="text-sm text-muted">
              {t("successHint", { code: bookResult.confirmation_code })}
            </p>
            <div className="flex flex-wrap gap-sm">
              <Link href="/bookings">
                <Button variant="ghost">{t("viewBookings")}</Button>
              </Link>
              {bookResult.trip_id ? (
                <Link href={`/trips/${bookResult.trip_id}`}>
                  <Button variant="ghost">{t("viewTrip")}</Button>
                </Link>
              ) : null}
              <Button onClick={closeBook}>{t("close")}</Button>
            </div>
          </div>
        ) : (
          <form onSubmit={submitBook} className="flex flex-col gap-md">
            <p className="text-sm text-muted">{t("oneSeatNotice")}</p>
            <Field
              label={t("nameLabel")}
              required
              value={bookForm.name}
              onChange={(e) =>
                setBookForm((prev) => ({ ...prev, name: e.target.value }))
              }
            />
            <Field
              label={t("emailLabel")}
              type="email"
              required
              value={bookForm.email}
              onChange={(e) =>
                setBookForm((prev) => ({ ...prev, email: e.target.value }))
              }
            />
            <Field
              label={t("phoneLabel")}
              required
              value={bookForm.phone}
              onChange={(e) =>
                setBookForm((prev) => ({ ...prev, phone: e.target.value }))
              }
            />
            <Select
              label={t("tripLabel")}
              value={tripId}
              onChange={(e) => setSelectedTripId(e.target.value)}
            >
              <option value="">{t("tripNone")}</option>
              {trips.map((trip) => (
                <option key={trip.id} value={trip.id}>
                  {trip.title}
                </option>
              ))}
            </Select>

            {bookError ? (
              <p role="alert" className="text-sm font-bold text-status-cancelled">
                {bookError}
              </p>
            ) : null}

            <div className="mt-sm flex justify-end gap-sm">
              <Button type="button" variant="ghost" onClick={closeBook}>
                {t("cancel")}
              </Button>
              <Button
                type="submit"
                disabled={
                  bookFlight.isPending ||
                  !bookForm.name.trim() ||
                  !bookForm.email.trim() ||
                  !bookForm.phone.trim()
                }
              >
                {bookFlight.isPending ? (
                  <Spinner label={t("submitting")} />
                ) : (
                  t("submitButton")
                )}
              </Button>
            </div>
          </form>
        )}
      </Modal>

      <UpgradeDialog
        open={upgradeOpen}
        hint={upgradeHint}
        onClose={() => setUpgradeOpen(false)}
      />
    </div>
  );
}
