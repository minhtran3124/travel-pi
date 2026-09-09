"use client";

import { useTranslations } from "next-intl";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { RoutePanel } from "@/components/chat/panel/RoutePanel";
import type { RoutePanelData } from "@/lib/stream/panel";
import { useRoute, type RouteResponse } from "@/lib/query/today";
import type { components } from "@/lib/api/schema";

type DayPlanItem = components["schemas"]["DayPlanItem"];

/**
 * Keyless Google Maps directions deep-link — derived exactly as the backend
 * panel builder does (`apps/api/app/streaming/panels/route.py:_gmaps_dir_url`)
 * so the reused `RoutePanel` gets the same link it does in chat.
 */
function gmapsDirUrl(
  oLat: number,
  oLng: number,
  dLat: number,
  dLng: number,
): string {
  return (
    "https://www.google.com/maps/dir/?api=1" +
    `&origin=${oLat},${oLng}&destination=${dLat},${dLng}`
  );
}

/** Project a service `RouteResponse` into the `RoutePanel` render model. */
function toPanelData(r: RouteResponse): RoutePanelData {
  return {
    origin: {
      name: r.origin.name,
      lat: r.origin.latitude,
      lng: r.origin.longitude,
    },
    destination: {
      name: r.destination.name,
      lat: r.destination.latitude,
      lng: r.destination.longitude,
    },
    recommended_mode: r.recommended_mode,
    legs: r.legs.map((leg) => ({
      mode: leg.mode,
      distance_km: leg.distance_km,
      duration_minutes: leg.duration_minutes,
    })),
    straight_line_km: r.straight_line_km,
    source: r.source,
    geometry: (r.geometry as [number, number][] | null | undefined) ?? null,
    gmaps_url: gmapsDirUrl(
      r.origin.latitude,
      r.origin.longitude,
      r.destination.latitude,
      r.destination.longitude,
    ),
  };
}

/**
 * Directions from the previous item to the next unstarted one, drawn through
 * the existing chat `RoutePanel` (map + mode chips + recommended leg + Maps
 * deep-link). Both items need a `place_id`; a hand-typed itinerary has none, so
 * the "unavailable" note — not an error — is the common state, and no route
 * request is made in it.
 */
export function TodayDirections({
  previous,
  next,
}: {
  previous: DayPlanItem | null;
  next: DayPlanItem | null;
}) {
  const t = useTranslations("Today.directions");
  const tErr = useTranslations("Errors");

  const fromId = previous?.item.place_id ?? "";
  const toId = next?.item.place_id ?? "";
  const { data, isPending, isError } = useRoute(fromId, toId);

  const canRoute = fromId.length > 0 && toId.length > 0;

  return (
    <section className="flex flex-col gap-md">
      <h2 className="text-lg font-extrabold text-ink">{t("title")}</h2>
      <Card className="flex flex-col">
        {!canRoute ? (
          <p className="text-sm text-muted">{t("unavailable")}</p>
        ) : isPending ? (
          <div className="flex items-center gap-sm text-sm text-muted">
            <Spinner label={t("title")} />
          </div>
        ) : isError || !data ? (
          // A failed route (react-query v5: isPending false, data undefined) must
          // not fall through to the spinner above — `!data` here means the query
          // settled without a body, i.e. an error, not "still loading".
          <EmptyState
            icon="⚠️"
            title={tErr("somethingWentWrongTitle")}
            hint={tErr("somethingWentWrongHint")}
          />
        ) : (
          <div className="h-[26rem] overflow-hidden rounded-sm">
            <RoutePanel data={toPanelData(data)} />
          </div>
        )}
      </Card>
    </section>
  );
}
