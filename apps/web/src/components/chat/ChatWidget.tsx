"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { qk } from "@/lib/api/keys";
import { useIdentity } from "@/lib/identity/useUserId";
import { panelKey } from "@/lib/stream/panel";
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
 * Signed-out surface: the agent requires a Supabase session (anonymous chat was
 * removed), so a logged-out visitor gets a sign-in invitation instead of the
 * composer — no `/agent/*` request is ever made. Renders a `<section>` so the
 * compact-sheet wrapper can size it exactly like {@link ChatPanel}.
 */
function SignedOutPrompt() {
  const t = useTranslations("Chat");
  return (
    <section
      role="dialog"
      aria-label={t("dialogLabel")}
      className="tp-chat-in relative flex h-[min(70vh,560px)] w-[min(92vw,400px)] flex-col items-center justify-center gap-md rounded-[20px] border border-line bg-panel px-xl text-center text-ink shadow-lift"
    >
      <p className="text-lg font-semibold">{t("greetingTitle")}</p>
      <Link
        href="/auth/login"
        className="rounded-pill bg-lime px-lg py-2 text-sm font-medium text-on-accent shadow-lift transition duration-150 hover:brightness-105"
      >
        {t("signInPrompt")}
      </Link>
    </section>
  );
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
  const [panelFocus, setPanelFocus] = useState<{ key: string; nonce: number } | null>(null);
  // Monotonic and independent of panelFocus so a chip click after a cleared
  // focus (a new panel streamed in) never restarts the nonce SidePanel saw.
  const focusNonce = useRef(0);
  const isCompact = useIsCompact();
  const launcherRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  // Only a confirmed signed-out session swaps in the sign-in prompt; `loading`
  // renders the panel as before so first paint never flashes the prompt.
  const signedOut = useIdentity().status === "signed-out";

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
  // Also clear any stale chip focus — a freshly streamed panel wins over an
  // earlier chip request; a later chip click sets a new focus anyway.
  // Render-phase adjust-on-change (no effect) — the React-recommended pattern.
  const newestPanelId = stream.panels[stream.panels.length - 1]?.toolCallId ?? null;
  const [seenPanelId, setSeenPanelId] = useState(newestPanelId);
  if (newestPanelId !== seenPanelId) {
    setSeenPanelId(newestPanelId);
    if (newestPanelId) {
      setMapHidden(false);
      setPanelFocus(null);
    }
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
          {signedOut ? (
            <SignedOutPrompt />
          ) : (
            <ChatPanel stream={stream} onClose={closeWidget} isCompact />
          )}
        </div>
      ) : null}

      {/* Launcher FAB stays fixed bottom-right in both layouts; at `sm`+ it also
          hosts the docked floating panel + drawer row. */}
      <div
        ref={launcherRef}
        className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-md"
      >
        {open && !isCompact && signedOut ? <SignedOutPrompt /> : null}
        {open && !isCompact && !signedOut ? (
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
                focusNonce.current += 1;
                setPanelFocus({ key: panelKey(panel), nonce: focusNonce.current });
              }}
            />
          </div>
        ) : null}
        <ChatLauncher open={open} onToggle={() => setOpen((v) => !v)} />
      </div>
    </>
  );
}
