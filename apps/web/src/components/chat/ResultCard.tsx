"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import type { PanelArtifact } from "@/lib/stream/panel";
import { PANEL_LABEL_KEYS, PANEL_RENDERERS } from "./panel/registry";

export interface ResultCardProps {
  panel: PanelArtifact;
  onOpen: (panel: PanelArtifact) => void;
}

// Lightweight kind glyphs, drawn in the same inline-SVG idiom as ChatEmptyState
// (stroke: currentColor, 24×24 viewBox). lucide-react is not a dependency of this
// app, so a per-kind <path> keeps the card self-contained — see SUMMARY Deviations.
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
// flat array under a well-known key. Anything else returns null → generic card.
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
 * A compact, in-turn summary of one panel artifact. Clicking anywhere on the
 * card promotes the artifact to its full renderer (via `onOpen`) — the heavy
 * renderer stays in the drawer/sheet and is NEVER mounted here. A `kind` with no
 * registered renderer renders nothing, matching `SidePanel`'s forward-compat gate.
 */
export function ResultCard({ panel, onOpen }: ResultCardProps) {
  const tPanel = useTranslations("Panel");
  const tChat = useTranslations("Chat");

  if (!PANEL_RENDERERS[panel.kind]) return null;

  const labelKey = PANEL_LABEL_KEYS[panel.kind];
  const title = labelKey ? tPanel(labelKey) : panel.kind;
  const count = itemCount(panel);
  // `Panel.places.results` is the catalog's generic "# result(s)" plural; reused
  // here as the count line for any list-like kind (localized in en + vi).
  const summary = count !== null ? tPanel("places.results", { count }) : null;

  return (
    <button
      type="button"
      onClick={() => onOpen(panel)}
      className="tp-card-in tp-glow group flex w-full items-center gap-sm rounded-md bg-panel px-md py-sm text-left transition duration-150 hover:-translate-y-0.5 active:translate-y-px"
    >
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-sm bg-panel-raised text-muted transition-colors duration-150 group-hover:bg-lime-soft group-hover:text-ink">
        <svg
          width="16"
          height="16"
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
      <span className="min-w-0 flex-1">
        <span className="block overflow-hidden text-ellipsis whitespace-nowrap text-sm font-semibold text-ink">
          {title}
        </span>
        {summary ? (
          <span className="mt-0.5 block overflow-hidden text-ellipsis whitespace-nowrap text-xs text-muted">
            {summary}
          </span>
        ) : null}
      </span>
      <span className="shrink-0 text-xs font-medium text-muted transition-colors duration-150 group-hover:text-ink">
        {tChat("result.open")}
      </span>
    </button>
  );
}
