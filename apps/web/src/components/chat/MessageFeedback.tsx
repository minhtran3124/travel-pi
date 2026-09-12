"use client";

import { useCallback, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import { cn } from "@/lib/cn";
import {
  useSubmitFeedback,
  type EffectiveFeedback,
  type FeedbackAction,
  type FeedbackResponse,
} from "@/lib/query/feedback";
import { FeedbackDialog, type FeedbackDetail } from "./FeedbackDialog";

type Rating = "helpful" | "not_helpful";

/** What the controls show — derived from the server's effective state. */
interface View {
  rating: Rating | null;
  /** A detail event exists for the active negative rating. */
  hasDetail: boolean;
}

type Status = "idle" | "saving" | "saved" | "removed" | "error";

/** One logical action: enough to re-apply its optimistic state and roll back. */
interface Action {
  kind: "rating" | "retract" | "detail";
  prev: View;
  optimistic: View;
}

function toView(f: EffectiveFeedback | null | undefined): View {
  return {
    rating: f?.rating ?? null,
    hasDetail: Boolean(f && (f.reason_code || f.comment_present)),
  };
}

/** The BE error envelope carries `status_code` (app/schemas/error.py). */
function statusCodeOf(err: unknown): number | undefined {
  if (typeof err !== "object" || err === null) return undefined;
  const code = (err as { status_code?: unknown }).status_code;
  return typeof code === "number" ? code : undefined;
}

const svgProps = {
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

// 40px hit area (DESIGN §8.4); the pressed state is carried by aria-pressed
// AND the border/fill, never by colour alone.
const thumbClass =
  "inline-flex h-10 min-w-10 items-center gap-xs rounded-[10px] border border-transparent px-sm text-xs font-bold text-muted transition duration-150 hover:text-ink aria-pressed:border-ink aria-pressed:bg-lime-soft aria-pressed:text-ink disabled:cursor-not-allowed disabled:opacity-50";

const linkButtonClass =
  "inline-flex h-10 items-center rounded-[10px] px-sm text-xs font-bold text-ink underline underline-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

export interface MessageFeedbackProps {
  /** The persisted assistant message id (never a client render id). */
  assistantMessageId: string;
  /** Effective state reloaded from history; `null`/absent when unrated. */
  initial?: EffectiveFeedback | null;
}

/**
 * Thumbs up / down under an assistant reply (DESIGN §8). Optimistic per
 * DESIGN §7.2: snapshot → show the new state and disable only this message's
 * controls → POST → replace with the canonical state; on failure roll back and
 * offer a retry that replays the same client event id. A `404` means the
 * message cannot be rated (e.g. the persisted fallback of a failed turn): the
 * controls disappear without a toast.
 */
export function MessageFeedback({
  assistantMessageId,
  initial,
}: MessageFeedbackProps) {
  const t = useTranslations("Chat.feedback");
  const locale = useLocale();
  const { submit, retry } = useSubmitFeedback();
  const [view, setView] = useState<View>(() => toView(initial));
  const [status, setStatus] = useState<Status>("idle");
  // Disables only THIS message's controls while its request is pending — the
  // hook's in-flight guard is keyed on the message id, so a different action
  // during that window would otherwise share the first request's promise.
  const [busy, setBusy] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  /** `null` = closed; otherwise the detail request state shown in the dialog. */
  const [dialog, setDialog] = useState<"idle" | "saving" | "error" | null>(null);
  const lastAction = useRef<Action | null>(null);

  const run = useCallback(
    async (request: Promise<FeedbackResponse | undefined>, action: Action) => {
      setBusy(true);
      try {
        const res = await request;
        if (!res) return;
        setView(toView(res.effective_feedback));
        setStatus(action.kind === "retract" ? "removed" : "saved");
        if (action.kind === "detail") setDialog(null);
      } catch (err) {
        if (statusCodeOf(err) === 404) {
          setUnavailable(true);
          return;
        }
        setView(action.prev);
        if (action.kind === "detail") setDialog("error");
        else setStatus("error");
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const rate = (rating: Rating) => {
    if (busy) return;
    const retract = view.rating === rating;
    const action: Action = {
      kind: retract ? "retract" : "rating",
      prev: view,
      optimistic: { rating: retract ? null : rating, hasDetail: false },
    };
    const body: FeedbackAction = retract
      ? { assistant_message_id: assistantMessageId, action: "retract_rating", locale }
      : { assistant_message_id: assistantMessageId, action: "set_rating", rating, locale };
    lastAction.current = action;
    setView(action.optimistic);
    setStatus("saving");
    void run(submit(body), action);
  };

  const saveDetail = (detail: FeedbackDetail) => {
    if (busy) return;
    const action: Action = { kind: "detail", prev: view, optimistic: view };
    lastAction.current = action;
    setDialog("saving");
    void run(
      submit({
        assistant_message_id: assistantMessageId,
        action: "add_detail",
        reason_code: detail.reasonCode,
        comment: detail.comment,
        locale,
      }),
      action,
    );
  };

  const onRetry = () => {
    const action = lastAction.current;
    if (!action || busy) return;
    setView(action.optimistic);
    if (action.kind === "detail") setDialog("saving");
    else setStatus("saving");
    void run(retry(assistantMessageId), action);
  };

  if (unavailable) return null;

  const statusText =
    status === "saving"
      ? t("saving")
      : status === "saved"
        ? t("saved")
        : status === "removed"
          ? t("removed")
          : status === "error"
            ? t("error")
            : "";

  return (
    <>
      <div
        role="group"
        aria-label={t("groupLabel")}
        className="flex flex-wrap items-center gap-xs"
      >
        <button
          type="button"
          aria-pressed={view.rating === "helpful"}
          disabled={busy}
          onClick={() => rate("helpful")}
          className={thumbClass}
        >
          <svg {...svgProps} fill={view.rating === "helpful" ? "currentColor" : "none"}>
            <path d="M7 10v12" />
            <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" />
          </svg>
          {t("helpful")}
        </button>
        <button
          type="button"
          aria-pressed={view.rating === "not_helpful"}
          disabled={busy}
          onClick={() => rate("not_helpful")}
          className={thumbClass}
        >
          <svg {...svgProps} fill={view.rating === "not_helpful" ? "currentColor" : "none"}>
            <path d="M17 14V2" />
            <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z" />
          </svg>
          {t("notHelpful")}
        </button>
        {view.rating === "not_helpful" && !view.hasDetail ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => setDialog("idle")}
            className={linkButtonClass}
          >
            {t("tellUsMore")}
          </button>
        ) : null}
        <span
          role="status"
          aria-live="polite"
          className={cn("text-xs", status === "error" ? "text-coral-ink" : "text-muted")}
        >
          {statusText}
        </span>
        {status === "error" ? (
          <button
            type="button"
            disabled={busy}
            onClick={onRetry}
            className={linkButtonClass}
          >
            {t("retry")}
          </button>
        ) : null}
      </div>
      {dialog !== null ? (
        <FeedbackDialog
          open
          status={dialog}
          onSave={saveDetail}
          onRetry={onRetry}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </>
  );
}
