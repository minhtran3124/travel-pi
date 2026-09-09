"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { FlightResultCard } from "@/components/flights/FlightResultCard";
import { PanelIntlProvider } from "@/components/chat/panel/PanelIntlProvider";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import {
  useFlightSearch,
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

export default function FlightsPage() {
  const t = useTranslations("Flights");
  const locale = useLocale();

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
        <div className="flex flex-col gap-sm">
          <p className="text-sm text-muted">{t("bookViaAssistantHint")}</p>
          <PanelIntlProvider language={locale}>
            <div className="flex flex-col gap-sm">
              {results.map((f) => (
                <FlightResultCard
                  key={f.id}
                  f={toPanelFlight(f)}
                  cheapest={f.price === cheapestPrice}
                />
              ))}
            </div>
          </PanelIntlProvider>
        </div>
      )}
    </div>
  );
}
