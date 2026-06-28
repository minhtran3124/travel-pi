"use client";

import { useMemo, useState } from "react";

import { cn } from "@/lib/cn";
import type { PanelArtifact } from "@/lib/stream/panel";
import { PANEL_LABELS, PANEL_RENDERERS } from "./registry";

/**
 * The detail drawer that springs out to the left of the chat panel. Shows the
 * structured payload tools emit (a route map today), one tab per renderable
 * `kind`; selecting a tab swaps the body. Renders nothing when no panel has a
 * registered renderer, so the parent can gate purely on `panels.length`.
 */
export function SidePanel({
  panels,
  onClose,
}: {
  panels: PanelArtifact[];
  onClose: () => void;
}) {
  const renderable = useMemo(
    () => panels.filter((p) => PANEL_RENDERERS[p.kind]),
    [panels],
  );
  const [activeKind, setActiveKind] = useState<string | null>(null);
  const active =
    renderable.find((p) => p.kind === activeKind) ??
    renderable[renderable.length - 1];

  if (!active) return null;
  const Renderer = PANEL_RENDERERS[active.kind];
  const kinds = Array.from(new Set(renderable.map((p) => p.kind)));

  return (
    <section
      aria-label="Detail panel"
      className="tp-chat-in flex h-[min(70vh,560px)] w-[min(92vw,440px)] flex-col overflow-hidden rounded-[20px] border border-line bg-white text-ink shadow-lift"
    >
      <header className="flex items-center justify-between border-b border-line px-lg py-sm">
        <div className="flex gap-xs">
          {kinds.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setActiveKind(k)}
              className={cn(
                "rounded-full px-sm py-xs text-xs font-medium transition",
                k === active.kind
                  ? "bg-ink text-white"
                  : "text-muted hover:bg-surface",
              )}
            >
              {PANEL_LABELS[k] ?? k}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Hide panel"
          className="text-sm text-muted transition hover:text-ink"
        >
          ✕
        </button>
      </header>
      <div className="min-h-0 flex-1">
        <Renderer data={active.data} />
      </div>
    </section>
  );
}
