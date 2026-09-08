"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";

export interface UpgradeDialogProps {
  open: boolean;
  /** `PremiumRequiredError.hint`, when the BE sent one. */
  hint?: string;
  onClose: () => void;
}

/**
 * Shown when a book call comes back 403 (`PremiumRequiredError`). Composed
 * from the shared `Modal` the way `ConfirmDialog` is — a single dismissive
 * action, since there is no upgrade flow to route into yet.
 */
export function UpgradeDialog({ open, hint, onClose }: UpgradeDialogProps) {
  const t = useTranslations("Booking.upgrade");
  return (
    <Modal open={open} onClose={onClose} title={t("title")}>
      <p className="-mt-xs mb-md text-sm text-muted">{hint ?? t("message")}</p>
      <div className="mt-sm flex justify-end">
        <Button onClick={onClose}>{t("close")}</Button>
      </div>
    </Modal>
  );
}
