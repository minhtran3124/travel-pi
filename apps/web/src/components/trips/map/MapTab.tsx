"use client";

import { useTranslations } from "next-intl";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { TripMap, type TripMapMarker } from "@/components/map/TripMap";
import { useTrip, type TripDetail } from "@/lib/query/trips";

// Neutral marker for a shortlisted place with no itinerary day of its own.
const SAVED_COLOR = "#64748b";

// Distinct hues cycling per itinerary day, so day 9 reuses day 1's color
// rather than running out of a fixed palette.
const DAY_COLORS = [
  "#2563eb",
  "#dc2626",
  "#059669",
  "#d97706",
  "#7c3aed",
  "#db2777",
  "#0891b2",
  "#65a30d",
];

function dayColor(day: number): string {
  return DAY_COLORS[(day - 1) % DAY_COLORS.length];
}

type Translate = ReturnType<typeof useTranslations>;

interface Located {
  name: string;
  lat: number;
  lng: number;
}

/**
 * The trip's shortlisted places, resolved to a marker each (skipping any
 * without coordinates), plus a lookup by place id/short_code so itinerary
 * items carrying a `place_id` can resolve to the same coordinates — a
 * TripItem has no lat/lng of its own.
 */
function resolvePlaces(
  trip: TripDetail,
  t: Translate,
): { markers: TripMapMarker[]; byRef: Map<string, Located> } {
  const markers: TripMapMarker[] = [];
  const byRef = new Map<string, Located>();

  for (const entry of trip.places ?? []) {
    const place = entry.place;
    if (place.latitude == null || place.longitude == null) continue;
    const located: Located = {
      name: place.name,
      lat: place.latitude,
      lng: place.longitude,
    };
    byRef.set(place.id, located);
    byRef.set(place.short_code, located);
    markers.push({
      position: { lat: located.lat, lng: located.lng },
      label: t("markerSaved", { name: located.name }),
      color: SAVED_COLOR,
    });
  }

  return { markers, byRef };
}

/** Build every marker: shortlisted places, plus dated itinerary items with a place_id. */
export function buildMarkers(trip: TripDetail, t: Translate): TripMapMarker[] {
  const { markers, byRef } = resolvePlaces(trip, t);

  for (const item of trip.items ?? []) {
    if (!item.place_id) continue;
    const located = byRef.get(item.place_id);
    if (!located) continue;
    markers.push({
      position: { lat: located.lat, lng: located.lng },
      label: t("markerItinerary", { day: item.day, title: item.title }),
      color: dayColor(item.day),
    });
  }

  return markers;
}

export function MapTab({ tripId }: { tripId: string }) {
  const t = useTranslations("Map");
  const { data: trip, isPending, isError } = useTrip(tripId);
  const markers = trip ? buildMarkers(trip, t) : [];

  return (
    <section className="flex flex-col gap-md">
      <h2 className="text-lg font-extrabold text-ink">{t("title")}</h2>
      <Card className="flex flex-col">
        {isPending ? (
          <div className="flex items-center gap-sm text-sm text-muted">
            <Spinner label={t("loadingLabel")} />
            <span>{t("loading")}</span>
          </div>
        ) : isError || !trip ? (
          <EmptyState icon="🗺️" title={t("errorTitle")} hint={t("errorHint")} />
        ) : markers.length === 0 ? (
          <EmptyState icon="📍" title={t("emptyTitle")} hint={t("emptyHint")} />
        ) : (
          <TripMap
            className="h-[28rem] w-full rounded-sm"
            ariaLabel={t("ariaLabel")}
            markers={markers}
          />
        )}
      </Card>
    </section>
  );
}
