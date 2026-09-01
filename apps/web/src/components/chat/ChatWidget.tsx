"use client";

import { useQueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { qk } from "@/lib/api/keys";
import { ChatLauncher } from "./ChatLauncher";
import { ChatPanel } from "./ChatPanel";
import { PanelIntlProvider } from "./panel/PanelIntlProvider";
import { SidePanel } from "./panel/SidePanel";
import { useAgentStream } from "./useAgentStream";

/** Extract a trip id from a `/trips/{id}` route, else undefined. */
function tripIdFromPath(pathname: string | null): string | undefined {
  if (!pathname) return undefined;
  const match = pathname.match(/^\/trips\/([^/]+)/);
  return match?.[1];
}

/**
 * Layout contract for the chat shell.
 *
 * `isCompact === true` below the Tailwind `sm` breakpoint (viewport < 640px):
 * the open widget becomes a full-viewport sheet and the `SidePanel` drawer is
 * never rendered beside it (panels are reached through inline result cards).
 * `isCompact === false` at `sm`+ keeps the docked floating panel + drawer row.
 *
 * The rest of the redesign relies on this single boolean as the mobile/desktop
 * decision — it is the only responsive switch in the chat module.
 */
function useIsCompact(): boolean {
  const [isCompact, setIsCompact] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639.98px)");
    const update = () => setIsCompact(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return isCompact;
}

/**
 * Kith-style agent co-pilot. Composes the launcher FAB + chat panel, manages
 * open state, derives the active trip from the route, and refreshes the
 * planner's trip queries once an assistant turn completes (the agent may have
 * mutated trip data server-side).
 *
 * Responsive shell (design.md §3 Fork 3): below `sm` the open widget is a
 * full-height sheet with no side drawer; at `sm`+ it is the docked floating
 * panel + drawer row. The launcher FAB stays fixed bottom-right in both.
 */
export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [mapHidden, setMapHidden] = useState(false);
  // Tab request for the drawer: set when an inline result card is clicked.
  const [panelFocus, setPanelFocus] = useState<{ kind: string; nonce: number } | null>(null);
  const isCompact = useIsCompact();
  const launcherRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  // Restore focus to the launcher when the compact sheet closes (a11y: the
  // trigger regains focus once the modal dialog is dismissed).
  const closeWidget = useCallback(() => {
    setOpen(false);
    if (isCompact) {
      requestAnimationFrame(() =>
        launcherRef.current?.querySelector("button")?.focus(),
      );
    }
  }, [isCompact]);
  const tripId = tripIdFromPath(pathname);
  const queryClient = useQueryClient();

  const onTurnComplete = useCallback(() => {
    if (!tripId) return;
    queryClient.invalidateQueries({ queryKey: qk.trip(tripId) });
    queryClient.invalidateQueries({ queryKey: qk.items(tripId) });
    queryClient.invalidateQueries({ queryKey: qk.budget(tripId) });
    queryClient.invalidateQueries({ queryKey: qk.expenses(tripId) });
  }, [queryClient, tripId]);

  const stream = useAgentStream({ tripId, onTurnComplete });

  // Re-surface the drawer when a new panel streams in: a prior "Hide" must not
  // latch it shut against a freshly-produced panel (e.g. weather after a route).
  // Render-phase adjust-on-change (no effect) — the React-recommended pattern.
  const newestPanelId = stream.panels[stream.panels.length - 1]?.toolCallId ?? null;
  const [seenPanelId, setSeenPanelId] = useState(newestPanelId);
  if (newestPanelId !== seenPanelId) {
    setSeenPanelId(newestPanelId);
    if (newestPanelId) setMapHidden(false);
  }

  // The agent co-pilot is part of the app shell, not the auth surfaces.
  if (pathname?.startsWith("/auth")) {
    return null;
  }

  const hasPanels = stream.panels.length > 0;
  const showDrawer = open && hasPanels && !mapHidden;

  return (
    <>
      {/* Below `sm`: a full-viewport sheet. The drawer is never rendered here —
          panels are reached through inline result cards. The wrapper forces the
          panel's own `<section>` to fill the sheet without editing ChatPanel. */}
      {open && isCompact ? (
        <div
          data-testid="chat-sheet"
          className="fixed inset-0 z-50 [&>section]:h-dvh [&>section]:w-full [&>section]:rounded-none [&>section]:border-0"
        >
          <ChatPanel stream={stream} onClose={closeWidget} isCompact />
        </div>
      ) : null}

      {/* Launcher FAB stays fixed bottom-right in both layouts; at `sm`+ it also
          hosts the docked floating panel + drawer row. */}
      <div
        ref={launcherRef}
        className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-md"
      >
        {open && !isCompact ? (
          <div data-testid="chat-docked" className="flex flex-row items-end gap-md">
            {showDrawer ? (
              <PanelIntlProvider language={stream.panelLanguage}>
                <SidePanel
                  panels={stream.panels}
                  onClose={() => setMapHidden(true)}
                  focus={panelFocus ?? undefined}
                />
              </PanelIntlProvider>
            ) : null}
            <ChatPanel
              stream={stream}
              onClose={() => setOpen(false)}
              onOpenPanel={(panel) => {
                setMapHidden(false);
                setPanelFocus((f) => ({ kind: panel.kind, nonce: (f?.nonce ?? 0) + 1 }));
              }}
            />
          </div>
        ) : null}
        <ChatLauncher open={open} onToggle={() => setOpen((v) => !v)} />
      </div>
    </>
  );
}
