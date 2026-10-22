"use client";

import { useTranslations } from "next-intl";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { cn } from "@/lib/cn";
import type { PanelArtifact } from "@/lib/stream/panel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ChatComposer } from "./ChatComposer";
import { ChatEmptyState } from "./ChatEmptyState";
import { ChatHeader, type AgentStatus } from "./ChatHeader";
import { ChatSuggestions } from "./ChatSuggestions";
import { InterruptPrompt } from "./InterruptPrompt";
import { MessageList } from "./MessageList";
import { PanelIntlProvider } from "./panel/PanelIntlProvider";
import { SidePanel } from "./panel/SidePanel";
import type { UseAgentStream } from "./useAgentStream";

export interface ChatPanelProps {
  stream: UseAgentStream;
  onClose: () => void;
  /**
   * Compact (mobile) sheet mode. Turns the panel into an `aria-modal` dialog
   * that traps focus, closes on Escape, locks body scroll, and promotes a
   * result card into an in-sheet bottom sheet instead of the desktop drawer.
   */
  isCompact?: boolean;
  /**
   * Promote a result card to the full renderer on desktop — the widget routes
   * this to its side-panel drawer. Unused in compact mode, which opens an
   * in-sheet bottom sheet instead.
   */
  onOpenPanel?: (panel: PanelArtifact) => void;
  /** A widget-level notice shown between the transcript and the composer. */
  notice?: ReactNode;
}

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * The agent's surface: a floating white panel that springs out of the launcher,
 * carrying the agent's identity + live status, a teaching empty state, the
 * streaming transcript, and a composer. Surfaces an amber notice when the agent
 * has degraded/failed.
 *
 * Exactly one non-transcript band shows at a time: an HITL interrupt checkpoint,
 * else a retry prompt after a failed turn, else the composer (which carries the
 * follow-up chip rail). Rich results attach to their turn as inline result
 * cards; "Open" promotes them to the desktop drawer or, in compact mode, an
 * in-sheet bottom sheet.
 */
export function ChatPanel({
  stream,
  onClose,
  isCompact = false,
  onOpenPanel,
  notice,
}: ChatPanelProps) {
  const t = useTranslations("Chat");
  const {
    messages,
    send,
    stop,
    isStreaming,
    error,
    interrupt,
    resume,
    canRetry,
    retry,
    regenerate,
    newConversation,
    suggestions,
    panelLanguage,
  } = stream;
  const [fullscreen, setFullscreen] = useState(false);
  const [confirmNew, setConfirmNew] = useState(false);
  // The panel promoted into the compact in-sheet bottom sheet, if any.
  const [sheetPanel, setSheetPanel] = useState<PanelArtifact | null>(null);
  const sectionRef = useRef<HTMLElement>(null);

  // Confirm only when there's something to lose; an empty chat resets silently.
  const handleNewConversation = () => {
    if (messages.length > 0) {
      setConfirmNew(true);
      return;
    }
    newConversation();
  };

  // Open a result card's full renderer: desktop delegates to the widget's
  // drawer; compact raises an in-sheet bottom sheet over the transcript.
  const handleOpenPanel = useCallback(
    (panel: PanelArtifact) => {
      if (isCompact) {
        setSheetPanel(panel);
        return;
      }
      onOpenPanel?.(panel);
    },
    [isCompact, onOpenPanel],
  );

  // Regenerate the last turn: reuse the error-gated retry when it applies,
  // otherwise drop the answer and re-run the saved question (retry: true —
  // no duplicate user bubble, no re-saved question row).
  const handleRegenerate = useCallback(() => {
    if (canRetry) {
      retry();
      return;
    }
    regenerate();
  }, [canRetry, retry, regenerate]);

  // Compact sheet a11y: lock body scroll while the sheet is open.
  useEffect(() => {
    if (!isCompact) return;
    document.body.classList.add("overflow-hidden");
    return () => document.body.classList.remove("overflow-hidden");
  }, [isCompact]);

  // Compact sheet a11y: focus the dialog on open so the trap has an anchor.
  useEffect(() => {
    if (!isCompact) return;
    sectionRef.current?.focus();
  }, [isCompact]);

  // Compact sheet a11y: Escape closes; Tab cycles focus within the sheet.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLElement>) => {
    if (!isCompact) return;
    if (e.key === "Escape") {
      e.stopPropagation();
      if (sheetPanel) {
        setSheetPanel(null);
        return;
      }
      onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const focusables = sectionRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
    if (!focusables || focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const inputBlocked = isStreaming || interrupt !== null;
  const status: AgentStatus =
    interrupt !== null ? "waiting" : isStreaming ? "working" : "ready";

  // The follow-up rail rides the composer; suppress it while streaming or during
  // an interrupt (the composer branch already excludes interrupt / retry).
  const showRail =
    messages.length > 0 && !isStreaming && suggestions.length > 0;

  return (
    <section
      ref={sectionRef}
      role="dialog"
      aria-label={t("dialogLabel")}
      aria-modal={isCompact ? true : undefined}
      tabIndex={isCompact ? -1 : undefined}
      onKeyDown={handleKeyDown}
      className={cn(
        "tp-chat-in relative flex flex-col overflow-hidden rounded-[20px] border border-line bg-panel text-ink shadow-lift",
        fullscreen
          ? "h-[80vh] w-[min(92vw,640px)]"
          : "h-[min(70vh,560px)] w-[min(92vw,400px)]",
      )}
    >
      <ChatHeader
        status={status}
        fullscreen={fullscreen}
        onToggleFullscreen={() => setFullscreen((v) => !v)}
        onClose={onClose}
        onNewConversation={handleNewConversation}
        isCompact={isCompact}
      />

      {error ? (
        <p
          role="status"
          className="border-b border-status-estimated/30 bg-status-estimated/10 px-lg py-sm text-xs font-medium text-status-estimated"
        >
          {error}
        </p>
      ) : null}

      {messages.length === 0 ? (
        <ChatEmptyState onPick={send} disabled={inputBlocked} />
      ) : (
        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          onOpenPanel={handleOpenPanel}
          onRegenerate={handleRegenerate}
        />
      )}

      {notice}

      {interrupt !== null ? (
        <InterruptPrompt
          draft={interrupt.payload.draft}
          onApprove={() => resume(true)}
          onReject={() => resume(false)}
        />
      ) : canRetry ? (
        <div className="flex items-center justify-between gap-sm border-t border-line bg-panel-raised px-lg py-sm">
          <span className="text-xs text-muted">{t("retryHint")}</span>
          <button
            type="button"
            onClick={retry}
            className="shrink-0 rounded-pill border border-line px-md py-1 text-xs font-medium text-ink transition hover:bg-line/40"
          >
            {t("retry")}
          </button>
        </div>
      ) : (
        <ChatComposer
          disabled={inputBlocked}
          onSend={send}
          isStreaming={isStreaming}
          onStop={stop}
          suggestions={
            showRail ? (
              <ChatSuggestions
                suggestions={suggestions}
                onPick={send}
                disabled={inputBlocked}
              />
            ) : undefined
          }
        />
      )}

      {/* Compact-only: an in-sheet bottom sheet promoting a result card to its
          full renderer, so a phone never puts the drawer beside the panel. */}
      {isCompact && sheetPanel ? (
        <div className="absolute inset-x-0 bottom-0 top-1/3 z-10 flex flex-col overflow-hidden border-t border-line bg-panel [&>section]:h-full [&>section]:w-full [&>section]:rounded-none [&>section]:border-0 [&>section]:shadow-none">
          <PanelIntlProvider language={panelLanguage}>
            <SidePanel panels={[sheetPanel]} onClose={() => setSheetPanel(null)} />
          </PanelIntlProvider>
        </div>
      ) : null}

      <ConfirmDialog
        open={confirmNew}
        title={t("newConversation")}
        message={t("newConversationConfirm")}
        confirmLabel={t("newConversationCta")}
        onConfirm={() => {
          setConfirmNew(false);
          newConversation();
        }}
        onCancel={() => setConfirmNew(false)}
      />
    </section>
  );
}
