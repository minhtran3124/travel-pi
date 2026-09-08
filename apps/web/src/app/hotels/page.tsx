"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { UpgradeDialog } from "@/components/booking/UpgradeDialog";
import { PanelIntlProvider } from "@/components/chat/panel/PanelIntlProvider";
import { HotelResultCard } from "@/components/hotels/HotelResultCard";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { client, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useTrips } from "@/lib/query/trips";
import {
  PremiumRequiredError,
  useBookHotel,
  type Booking,
} from "@/lib/query/hotels";

type HotelAvailability = components["schemas"]["HotelAvailability"];

// /hotels/search (Task 4.2's useHotelSearch) has no dates/party-size params —
// it's the date-less browse endpoint. This page needs `available`/`total_price`
// for specific dates and a party, which only /hotels/availability returns, so
// it queries that endpoint directly rather than adding a new lib/query hook
// (out of this task's declared file set).
type AvailabilityFilters = {
  city: string;
  check_in: string;
  check_out: string;
  rooms: number;
  adults: number;
  children: number;
};

function useHotelAvailability(filters: AvailabilityFilters | null) {
  return useQuery({
    queryKey: ["hotelAvailability", filters] as const,
    enabled: filters !== null,
    queryFn: () =>
      unwrap(
        client.GET("/hotels/availability", {
          params: { query: filters as AvailabilityFilters },
        }),
      ),
  });
}

const EMPTY_BOOK_FORM = { name: "", email: "", phone: "" };

export default function HotelsPage() {
  const t = useTranslations("Hotels");
  const locale = useLocale();
  const searchParams = useSearchParams();
  const prefilledTripId = searchParams.get("tripId") ?? "";

  const [city, setCity] = useState("");
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [rooms, setRooms] = useState("1");
  const [adults, setAdults] = useState("2");
  const [children, setChildren] = useState("0");
  const [submitted, setSubmitted] = useState<AvailabilityFilters | null>(null);

  const { data, isLoading, isError } = useHotelAvailability(submitted);
  const results = data?.results ?? [];
  const cheapestTotal = results.length
    ? Math.min(...results.map((h) => h.total_price))
    : null;

  const { data: tripsData } = useTrips();
  const trips = tripsData?.results ?? [];

  const [bookTarget, setBookTarget] = useState<HotelAvailability | null>(null);
  const [bookForm, setBookForm] = useState(EMPTY_BOOK_FORM);
  const [tripId, setTripId] = useState("");

  // A `?tripId=` link can point at a trip that's since been deleted, or one
  // the current user doesn't own — once trips have loaded, drop a prefilled
  // selection that isn't among them so the form doesn't silently submit an
  // id that 404s instead of showing "no trip" as it should.
  useEffect(() => {
    if (!prefilledTripId || tripsData === undefined) return;
    if (!trips.some((trip) => trip.id === prefilledTripId)) {
      setTripId((current) => (current === prefilledTripId ? "" : current));
    }
  }, [tripsData, prefilledTripId, trips]);
  const [bookResult, setBookResult] = useState<Booking | null>(null);
  const [bookError, setBookError] = useState<string | null>(null);
  const bookHotel = useBookHotel();

  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [upgradeHint, setUpgradeHint] = useState<string | undefined>(undefined);

  function search(e: React.FormEvent) {
    e.preventDefault();
    if (!city.trim() || !checkIn || !checkOut) return;
    const parsedRooms = Number.parseInt(rooms, 10);
    const parsedAdults = Number.parseInt(adults, 10);
    const parsedChildren = Number.parseInt(children, 10);
    setSubmitted({
      city: city.trim(),
      check_in: checkIn,
      check_out: checkOut,
      rooms: Number.isNaN(parsedRooms) ? 1 : Math.max(1, parsedRooms),
      adults: Number.isNaN(parsedAdults) ? 1 : Math.max(1, parsedAdults),
      children: Number.isNaN(parsedChildren) ? 0 : Math.max(0, parsedChildren),
    });
  }

  function openBook(hotel: HotelAvailability) {
    setBookTarget(hotel);
    setBookForm(EMPTY_BOOK_FORM);
    setTripId(prefilledTripId);
    setBookResult(null);
    setBookError(null);
  }

  function closeBook() {
    setBookTarget(null);
    setBookForm(EMPTY_BOOK_FORM);
    setBookResult(null);
    setBookError(null);
    bookHotel.reset();
  }

  async function submitBook(e: React.FormEvent) {
    e.preventDefault();
    if (!bookTarget || !submitted) return;
    setBookError(null);
    try {
      const booking = await bookHotel.mutateAsync({
        hotel_id: bookTarget.id,
        check_in: submitted.check_in,
        check_out: submitted.check_out,
        rooms: submitted.rooms,
        adults: submitted.adults,
        children: submitted.children,
        guest_name: bookForm.name.trim(),
        guest_email: bookForm.email.trim(),
        guest_phone: bookForm.phone.trim(),
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
          label={t("cityLabel")}
          placeholder={t("cityPlaceholder")}
          value={city}
          onChange={(e) => setCity(e.target.value)}
          wrapperClassName="min-w-[10rem]"
        />
        <Field
          label={t("checkInLabel")}
          type="date"
          value={checkIn}
          onChange={(e) => setCheckIn(e.target.value)}
          wrapperClassName="min-w-[10rem]"
        />
        <Field
          label={t("checkOutLabel")}
          type="date"
          value={checkOut}
          onChange={(e) => setCheckOut(e.target.value)}
          wrapperClassName="min-w-[10rem]"
        />
        <Field
          label={t("roomsLabel")}
          type="number"
          min={1}
          value={rooms}
          onChange={(e) => setRooms(e.target.value)}
          wrapperClassName="w-20"
        />
        <Field
          label={t("adultsLabel")}
          type="number"
          min={1}
          value={adults}
          onChange={(e) => setAdults(e.target.value)}
          wrapperClassName="w-20"
        />
        <Field
          label={t("childrenLabel")}
          type="number"
          min={0}
          value={children}
          onChange={(e) => setChildren(e.target.value)}
          wrapperClassName="w-20"
        />
        <Button type="submit" disabled={!city.trim() || !checkIn || !checkOut}>
          {t("searchButton")}
        </Button>
      </form>

      {submitted === null ? (
        <EmptyState icon="🏨" title={t("promptTitle")} hint={t("promptHint")} />
      ) : isLoading ? (
        <div className="flex justify-center py-xl">
          <Spinner label={t("loadingLabel")} />
        </div>
      ) : isError ? (
        <EmptyState icon="⚠️" title={t("errorTitle")} hint={t("errorHint")} />
      ) : results.length === 0 ? (
        <EmptyState icon="🏨" title={t("emptyTitle")} hint={t("emptyHint")} />
      ) : (
        <PanelIntlProvider language={locale}>
          <div className="flex flex-col gap-sm">
            {results.map((h) => (
              <div key={h.id} className="flex items-center gap-sm">
                <div className="flex-1">
                  <HotelResultCard h={h} cheapest={h.total_price === cheapestTotal} />
                </div>
                <Button onClick={() => openBook(h)}>{t("bookButton")}</Button>
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
              onChange={(e) => setTripId(e.target.value)}
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
                  bookHotel.isPending ||
                  !bookForm.name.trim() ||
                  !bookForm.email.trim() ||
                  !bookForm.phone.trim()
                }
              >
                {bookHotel.isPending ? (
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
