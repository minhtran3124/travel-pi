"use client";

import { useTranslations } from "next-intl";

import type { RoutePanelData } from "@/lib/stream/panel";
import { TripMap, type TripMapPosition } from "@/components/map/TripMap";

/** Route line points: the real ORS road path, or a straight fallback. */
function routeLine(d: RoutePanelData): TripMapPosition[] {
  if (d.geometry && d.geometry.length > 1) {
    return d.geometry.map(([lng, lat]) => ({ lat, lng }));
  }
  return [
    { lat: d.origin.lat, lng: d.origin.lng },
    { lat: d.destination.lat, lng: d.destination.lng },
  ];
}

function recommendedLeg(d: RoutePanelData) {
  return d.legs.find((l) => l.mode === d.recommended_mode) ?? d.legs[0];
}

/**
 * Route side-panel: a keyless MapLibre+OSM map drawing the route line (real ORS
 * road path when available, dashed straight line in estimate mode), origin /
 * destination markers, a recommended-mode duration·distance badge, per-mode
 * chips, and a keyless "Open in Google Maps" deep-link. MapLibre is imported
 * lazily inside the effect so the GL bundle loads only when a route is shown.
 */
export function RoutePanel({ data }: { data: RoutePanelData }) {
  const t = useTranslations("Panel");
  const leg = recommendedLeg(data);
  const isEstimate = !(data.geometry && data.geometry.length > 1);

  return (
    <div className="flex h-full flex-col">
      <TripMap
        className="min-h-0 flex-1"
        ariaLabel={t("route.mapLabel")}
        route={{ line: routeLine(data), dashed: isEstimate }}
        markers={[
          {
            position: { lat: data.origin.lat, lng: data.origin.lng },
            label: data.origin.name,
            color: "#0f172a",
          },
          {
            position: { lat: data.destination.lat, lng: data.destination.lng },
            label: data.destination.name,
            color: "#dc2626",
          },
        ]}
      />

      <div className="border-t border-line bg-panel px-lg py-md">
        <div className="flex items-center justify-between gap-md">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-ink">
              {data.origin.name} → {data.destination.name}
            </p>
            <p className="text-xs text-muted">
              {t("route.summary", {
                distance: leg.distance_km,
                duration: Math.round(leg.duration_minutes),
                mode: data.recommended_mode,
                estimated: data.source === "estimate" ? "true" : "false",
              })}
            </p>
          </div>
          <a
            href={data.gmaps_url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 rounded-full border border-line px-md py-xs text-xs font-medium text-ink transition hover:bg-panel-raised"
          >
            {t("route.openInGoogleMaps")}
          </a>
        </div>

        <div className="mt-sm flex flex-wrap gap-xs">
          {data.legs.map((l) => (
            <span
              key={l.mode}
              className={`rounded-full px-sm py-xs text-xs ${
                l.mode === data.recommended_mode
                  ? "bg-ink text-on-ink"
                  : "bg-panel-raised text-muted"
              }`}
            >
              {t("route.legChip", {
                mode: l.mode,
                distance: l.distance_km,
                duration: Math.round(l.duration_minutes),
              })}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
