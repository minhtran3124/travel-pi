"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { useEffect, useRef } from "react";

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

export interface TripMapPosition {
  lat: number;
  lng: number;
}

export interface TripMapMarker {
  position: TripMapPosition;
  label: string;
  color?: string;
  /** Short text drawn in a round badge instead of the default pin (e.g. a stop number). */
  badge?: string;
}

const BADGE_CLASS =
  "grid size-6 place-items-center rounded-pill bg-ink text-xs font-bold text-on-ink shadow-lift ring-2 ring-panel";

function badgeElement(text: string): HTMLElement {
  const el = document.createElement("div");
  el.className = BADGE_CLASS;
  el.textContent = text;
  return el;
}

export interface TripMapRoute {
  /** Ordered line points — the real road path, or a straight fallback. */
  line: TripMapPosition[];
  /** Draw the line dashed (used for an estimated, non-road-matched route). */
  dashed?: boolean;
}

export interface TripMapProps {
  markers: TripMapMarker[];
  route?: TripMapRoute;
  className?: string;
  ariaLabel?: string;
}

/**
 * Presentational MapLibre+OSM map: draws an optional route line and a set of
 * labeled markers. MapLibre is imported lazily inside the effect so the GL
 * bundle loads only when a map is actually shown. No data fetching here —
 * callers (the chat Route panel, the trip Map tab) supply markers/route.
 */
export function TripMap({ markers, route, className, ariaLabel }: TripMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

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

      const line: [number, number][] = (route?.line ?? []).map((p) => [p.lng, p.lat]);
      const center: [number, number] =
        line[0] ??
        (markers[0] ? [markers[0].position.lng, markers[0].position.lat] : [0, 0]);

      map = new maplibre.Map({
        container: containerRef.current,
        style: OSM_STYLE,
        attributionControl: { compact: true },
        center,
        zoom: 11,
      });

      map.on("load", () => {
        if (line.length > 1) {
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
              ...(route?.dashed ? { "line-dasharray": [2, 2] } : {}),
            },
          });
        }

        for (const marker of markers) {
          new maplibre.Marker(
            marker.badge
              ? { element: badgeElement(marker.badge) }
              : { color: marker.color },
          )
            .setLngLat([marker.position.lng, marker.position.lat])
            .setPopup(new maplibre.Popup().setText(marker.label))
            .addTo(map);
        }

        const bounds = new maplibre.LngLatBounds(center, center);
        for (const c of line) bounds.extend(c);
        for (const marker of markers) bounds.extend([marker.position.lng, marker.position.lat]);
        map.fitBounds(bounds, { padding: 48, maxZoom: 15, duration: 0 });
      });
    })();

    return () => {
      cancelled = true;
      if (map) map.remove();
    };
    /* eslint-enable @typescript-eslint/no-explicit-any */
  }, [markers, route]);

  return <div ref={containerRef} className={className} aria-label={ariaLabel} />;
}
