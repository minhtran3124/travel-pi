"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { panelSubLabel, type PanelArtifact } from "@/lib/stream/panel";
import { PANEL_LABEL_KEYS, PANEL_RENDERERS } from "./panel/registry";

export interface ResultChipsProps {
  panels: PanelArtifact[];
  onOpen: (panel: PanelArtifact) => void;
}

// Lightweight kind glyphs, drawn in the same inline-SVG idiom as ChatEmptyState
// (stroke: currentColor, 24×24 viewBox). lucide-react is not a dependency of this
// app, so a per-kind <path> keeps the chip self-contained.
const KIND_ICONS: Record<string, ReactNode> = {
  route: <path d="M6 19a3 3 0 1 0 0-6h12a3 3 0 1 0 0-6M6 5h.01M18 19h.01" />,
  places: (
    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0zM12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4z" />
  ),
  weather: (
    <path d="M12 3v1m0 16v1m9-9h-1M4 12H3m2.6-6.4.7.7m11.4-.7-.7.7M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.6 1.4A3.5 3.5 0 0 1 17 18H7z" />
  ),
  air_quality: (
    <path d="M3 8h11a3 3 0 1 0-3-3M3 16h15a3 3 0 1 1-3 3M3 12h9" />
  ),
  flights: (
    <path d="M17.8 19.2 16 11l3.5-3.5a2.1 2.1 0 0 0-3-3L13 8 4.8 6.2a.5.5 0 0 0-.5.8L8 11l-2 2H4l-1 2 4 1 1 4 2-1v-2l2-2 3.7 3.7a.5.5 0 0 0 .8-.5z" />
  ),
  hotels: (
    <path d="M4 20V6a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v14M14 8h4a2 2 0 0 1 2 2v10M2 20h20M8 8h2M8 12h2" />
  ),
};

// Per-kind count extractor for list-like payloads — cheap where the payload is a
// flat array under a well-known key. Anything else returns null → no count badge.
const COUNT_KEYS: Record<string, string> = {
  flights: "flights",
  hotels: "hotels",
  places: "places",
};

function itemCount(panel: PanelArtifact): number | null {
  const key = COUNT_KEYS[panel.kind];
  if (!key) return null;
  const data = panel.data;
  if (data && typeof data === "object") {
    const value = (data as Record<string, unknown>)[key];
    if (Array.isArray(value)) return value.length;
  }
  return null;
}

/**
 * One compact wrapping row of chips summarizing a turn's panel artifacts —
 * replaces the previous stack of full-width `ResultCard` rows so a turn with
 * several tool results costs one line, not one row per result. Clicking a chip
 * promotes the artifact to its full renderer (via `onOpen`) — the heavy renderer
 * stays in the drawer/sheet and is NEVER mounted here. A `kind` with no
 * registered renderer renders no chip, matching `SidePanel`'s forward-compat gate.
 */
export function ResultChips({ panels, onOpen }: ResultChipsProps) {
  const tPanel = useTranslations("Panel");
  const tChat = useTranslations("Chat");

  const renderable = panels.filter((panel) => PANEL_RENDERERS[panel.kind]);
  if (renderable.length === 0) return null;

  return (
    <div className="tp-card-in flex flex-wrap items-center gap-xs">
      {renderable.map((panel) => {
        const labelKey = PANEL_LABEL_KEYS[panel.kind];
        const subLabel = panelSubLabel(panel);
        const title = subLabel ?? (labelKey ? tPanel(labelKey) : panel.kind);
        const count = itemCount(panel);
        // `Panel.places.results` is the catalog's generic "# result(s)" plural;
        // reused as the accessible count for any list-like kind (en + vi).
        const summary =
          count !== null ? tPanel("places.results", { count }) : null;
        const label = `${title}${summary ? ` — ${summary}` : ""} (${tChat("result.open")})`;

        return (
          <button
            key={panel.toolCallId}
            type="button"
            onClick={() => onOpen(panel)}
            aria-label={label}
            title={label}
            className="tp-glow group inline-flex items-center gap-1.5 rounded-pill border border-line bg-panel py-1 pl-2 pr-2.5 text-xs font-medium text-ink transition duration-150 hover:-translate-y-0.5 hover:bg-panel-raised active:translate-y-px"
          >
            <span className="grid h-5 w-5 shrink-0 place-items-center rounded-pill bg-panel-raised text-muted transition-colors duration-150 group-hover:bg-lime-soft group-hover:text-ink">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                {KIND_ICONS[panel.kind] ?? KIND_ICONS.places}
              </svg>
            </span>
            {subLabel ? <span className="capitalize">{title}</span> : title}
            {count !== null ? (
              <span className="text-muted" aria-hidden="true">
                {count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
