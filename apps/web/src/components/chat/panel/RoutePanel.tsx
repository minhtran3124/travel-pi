"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";

import type { RoutePanelData } from "@/lib/stream/panel";

/** Keyless raster OSM style — no API key, dev-friendly tile source. */
const OSM_STYLE = {
  version: 8 as const,
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster" as const, source: "osm" }],
};

/** [lng, lat] line for the route: the real ORS road path, or a straight fallback. */
function routeLine(d: RoutePanelData): [number, number][] {
  if (d.geometry && d.geometry.length > 1) return d.geometry;
  return [
    [d.origin.lng, d.origin.lat],
    [d.destination.lng, d.destination.lat],
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
  const containerRef = useRef<HTMLDivElement | null>(null);
  const leg = recommendedLeg(data);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    // maplibre-gl is loaded lazily and used dynamically — treat as untyped here.
    /* eslint-disable @typescript-eslint/no-explicit-any */
    let map: any;

    void (async () => {
      const maplibre: any = (await import("maplibre-gl")).default;
      if (cancelled || !containerRef.current) return;

      const line = routeLine(data);
      const isEstimate = !(data.geometry && data.geometry.length > 1);

      map = new maplibre.Map({
        container: containerRef.current,
        style: OSM_STYLE,
        attributionControl: { compact: true },
        center: line[0],
        zoom: 11,
      });

      map.on("load", () => {
        map.addSource("route", {
          type: "geojson",
          data: {
            type: "Feature",
            geometry: { type: "LineString", coordinates: line },
            properties: {},
          },
        });
        map.addLayer({
          id: "route-line",
          type: "line",
          source: "route",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": "#2563eb",
            "line-width": 5,
            ...(isEstimate ? { "line-dasharray": [2, 2] } : {}),
          },
        });

        new maplibre.Marker({ color: "#0f172a" })
          .setLngLat([data.origin.lng, data.origin.lat])
          .setPopup(new maplibre.Popup().setText(data.origin.name))
          .addTo(map);
        new maplibre.Marker({ color: "#dc2626" })
          .setLngLat([data.destination.lng, data.destination.lat])
          .setPopup(new maplibre.Popup().setText(data.destination.name))
          .addTo(map);

        const bounds = new maplibre.LngLatBounds(line[0], line[0]);
        for (const c of line) bounds.extend(c);
        map.fitBounds(bounds, { padding: 48, maxZoom: 15, duration: 0 });
      });
    })();

    return () => {
      cancelled = true;
      if (map) map.remove();
    };
    /* eslint-enable @typescript-eslint/no-explicit-any */
  }, [data]);

  return (
    <div className="flex h-full flex-col">
      <div ref={containerRef} className="min-h-0 flex-1" aria-label={t("route.mapLabel")} />

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
