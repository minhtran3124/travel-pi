"use client";

import { useTranslations } from "next-intl";

import { Button } from "./Button";
import { Modal } from "./Modal";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  /** Body copy explaining the consequence of confirming. */
  message: string;
  /** Label for the affirmative action (e.g. "Start new", "Discard"). */
  confirmLabel: string;
  /** Defaults to the shared `Common.cancel` string. */
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * A yes/no confirmation on top of the shared {@link Modal}: ghost cancel +
 * primary confirm, matching the footer pattern used across the app's modals.
 * Replaces the native `window.confirm()` so destructive prompts follow the
 * design system (tokens, focus trap, Esc/backdrop dismissal).
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const t = useTranslations("Common");
  return (
    <Modal open={open} onClose={onCancel} title={title}>
      <p className="-mt-xs mb-md text-sm text-muted">{message}</p>
      <div className="mt-sm flex justify-end gap-sm">
        <Button variant="ghost" onClick={onCancel}>
          {cancelLabel ?? t("cancel")}
        </Button>
        <Button onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Modal>
  );
}
