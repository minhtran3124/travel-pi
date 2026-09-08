"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { cn } from "@/lib/cn";
import type { PanelArtifact } from "@/lib/stream/panel";
import { panelKey, panelSubLabel } from "@/lib/stream/panel";
import { PANEL_LABEL_KEYS, PANEL_RENDERERS } from "./registry";

/** External tab request: pins the tab for `key` when `nonce` changes. */
export type PanelFocus = { key: string; nonce: number };

/**
 * The detail drawer that springs out to the left of the chat panel. Shows the
 * structured payload tools emit (a route map today), one tab per renderable
 * panel (keyed by `panelKey`, so multiple places categories each get their
 * own tab); selecting a tab swaps the body. Renders nothing when no panel has
 * a registered renderer, so the parent can gate purely on `panels.length`.
 */
export function SidePanel({
  panels,
  onClose,
  focus,
}: {
  panels: PanelArtifact[];
  onClose: () => void;
  /**
   * Optional external tab request: when `nonce` changes, the tab for `key`
   * becomes active (an inline result card asking the drawer to show its
   * result). Uncontrolled otherwise.
   */
  focus?: PanelFocus;
}) {
  const t = useTranslations("Panel");
  const renderable = useMemo(
    () => panels.filter((p) => PANEL_RENDERERS[p.kind]),
    [panels],
  );
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const newest = renderable[renderable.length - 1];
  const newestId = newest?.toolCallId ?? null;

  // Surface a freshly-streamed panel: when a new panel arrives, drop any pinned
  // tab so `active` falls back to the newest. Without this, a new panel (e.g.
  // weather arriving while a route is shown) would only add a tab, never display.
  // Render-phase adjust-on-change (no effect) — the React-recommended pattern.
  const [seenNewestId, setSeenNewestId] = useState(newestId);
  let resolvedKey = activeKey;
  if (newestId !== seenNewestId) {
    setSeenNewestId(newestId);
    setActiveKey(null);
    resolvedKey = null;
  }

  // External focus request (same render-phase adjust-on-change pattern):
  // a changed nonce pins the requested key, winning over the newest-panel rule.
  const [seenFocusNonce, setSeenFocusNonce] = useState(focus?.nonce ?? null);
  if (focus && focus.nonce !== seenFocusNonce) {
    setSeenFocusNonce(focus.nonce);
    setActiveKey(focus.key);
    resolvedKey = focus.key;
  }

  const active =
    renderable.find((p) => panelKey(p) === resolvedKey) ?? newest;

  if (!active) return null;
  const Renderer = PANEL_RENDERERS[active.kind];

  return (
    <section
      aria-label={t("detailPanelLabel")}
      className="tp-chat-in flex h-[min(70vh,560px)] w-[min(92vw,440px)] flex-col overflow-hidden rounded-[20px] border border-line bg-panel text-ink shadow-lift"
    >
      <header className="flex items-center justify-between border-b border-line px-lg py-sm">
        <div className="flex gap-xs">
          {renderable.map((p) => {
            const key = panelKey(p);
            const subLabel = panelSubLabel(p);
            return (
              <button
                key={key}
                type="button"
                onClick={() => setActiveKey(key)}
                className={cn(
                  "rounded-full px-sm py-xs text-xs font-medium transition",
                  key === panelKey(active)
                    ? "bg-ink text-on-ink"
                    : "text-muted hover:bg-panel-raised",
                )}
              >
                {subLabel !== null ? (
                  <span className="capitalize">{subLabel}</span>
                ) : PANEL_LABEL_KEYS[p.kind] ? (
                  t(PANEL_LABEL_KEYS[p.kind])
                ) : (
                  p.kind
                )}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("hidePanel")}
          className="text-sm text-muted transition hover:text-ink"
        >
          ✕
        </button>
      </header>
      {/* Keyed by panelKey so a tab switch remounts the body and replays the
          short swap-in animation (a no-op under prefers-reduced-motion). */}
      <div key={panelKey(active)} className="tp-panel-swap min-h-0 flex-1">
        <Renderer data={active.data} />
      </div>
    </section>
  );
}
