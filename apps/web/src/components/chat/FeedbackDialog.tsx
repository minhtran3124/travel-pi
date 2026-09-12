"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Textarea } from "@/components/ui/Textarea";
import type { FeedbackReasonCode } from "@/lib/query/feedback";

/** Mirrors the BE `COMMENT_MAX_CHARS` (app/schemas/feedback.py). */
export const COMMENT_MAX_CHARS = 500;

/** Frozen public taxonomy (DESIGN §3.2) — order is the display order. */
const REASONS: FeedbackReasonCode[] = [
  "incorrect",
  "irrelevant",
  "incomplete",
  "unsafe",
  "other",
];

export interface FeedbackDetail {
  reasonCode: FeedbackReasonCode | null;
  /** Trimmed comment, `null` when empty. */
  comment: string | null;
}

export interface FeedbackDialogProps {
  open: boolean;
  /** Request state of the detail submission, owned by the parent. */
  status: "idle" | "saving" | "error";
  onSave: (detail: FeedbackDetail) => void;
  /** Replay the failed submission with the same client event id. */
  onRetry: () => void;
  /** Skip / Escape / backdrop — never retracts the saved rating (DESIGN §8.3). */
  onClose: () => void;
}

/**
 * "Tell us more" dialog for a negative rating (DESIGN §8.3): one optional
 * reason (native radios in a fieldset) plus an optional comment. Save needs at
 * least one of the two — the BE rejects an empty `add_detail`.
 */
export function FeedbackDialog({
  open,
  status,
  onSave,
  onRetry,
  onClose,
}: FeedbackDialogProps) {
  const t = useTranslations("Chat.feedback");
  const groupName = useId();
  const hintId = useId();
  const countId = useId();
  const [reason, setReason] = useState<FeedbackReasonCode | null>(null);
  const [comment, setComment] = useState("");
  // After a failure the primary button replays the SAME event until the user
  // edits the form — an edited payload is a new logical action (DESIGN §7.2).
  const [editedSinceError, setEditedSinceError] = useState(false);

  const trimmed = comment.trim();
  const canSave = (reason !== null || trimmed.length > 0) && status !== "saving";
  const retrying = status === "error" && !editedSinceError;

  function submit() {
    setEditedSinceError(false);
    onSave({ reasonCode: reason, comment: trimmed || null });
  }

  return (
    <Modal open={open} onClose={onClose} title={t("dialogTitle")}>
      <fieldset className="flex flex-col gap-xs">
        <legend className="mb-xs text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
          {t("reasonLegend")}
        </legend>
        {REASONS.map((code) => (
          <label
            key={code}
            className="flex min-h-10 cursor-pointer items-center gap-sm text-sm text-ink"
          >
            <input
              type="radio"
              name={groupName}
              value={code}
              checked={reason === code}
              onChange={() => {
                setReason(code);
                setEditedSinceError(true);
              }}
            />
            {t(`reasons.${code}`)}
          </label>
        ))}
      </fieldset>
      <div className="mt-md">
        <Textarea
          label={t("commentLabel")}
          value={comment}
          maxLength={COMMENT_MAX_CHARS}
          aria-describedby={`${hintId} ${countId}`}
          onChange={(e) => {
            setComment(e.target.value);
            setEditedSinceError(true);
          }}
        />
        <div className="mt-xs flex justify-between gap-sm text-xs text-muted">
          <span id={hintId}>{t("commentHint")}</span>
          <span id={countId}>
            {t("remaining", { count: COMMENT_MAX_CHARS - comment.length })}
          </span>
        </div>
      </div>
      <p aria-live="polite" className="mt-sm min-h-4 text-xs text-coral-ink">
        {status === "error" ? t("error") : null}
      </p>
      <div className="mt-sm flex justify-end gap-sm">
        <Button variant="ghost" onClick={onClose}>
          {t("skip")}
        </Button>
        <Button onClick={retrying ? onRetry : submit} disabled={!canSave}>
          {status === "saving" ? t("saving") : retrying ? t("retry") : t("save")}
        </Button>
      </div>
    </Modal>
  );
}
