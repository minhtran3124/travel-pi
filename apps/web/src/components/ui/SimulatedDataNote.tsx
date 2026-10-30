"use client";

import { useTranslations } from "next-intl";

import { Pill } from "@/components/ui/Pill";

/**
 * Flags flight/hotel results as synthetic inventory. Reads the `Panel` catalog,
 * so render it inside `PanelIntlProvider` (or any provider carrying `Panel`).
 */
export function SimulatedDataNote({ className }: { className?: string }) {
  const t = useTranslations("Panel");
  return (
    <div role="note" className={className}>
      <Pill variant="status" tone="estimated" label={t("simulatedData")} />
    </div>
  );
}
