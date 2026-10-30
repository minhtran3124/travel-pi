"use client";

import { useTranslations } from "next-intl";

/**
 * Flags flight/hotel results as synthetic inventory. Reads the `Panel` catalog,
 * so render it inside `PanelIntlProvider` (or any provider carrying `Panel`).
 */
export function SimulatedDataNote({ className }: { className?: string }) {
  const t = useTranslations("Panel");
  return (
    <p role="note" className={`text-xs text-muted ${className ?? ""}`.trim()}>
      {t("simulatedData")}
    </p>
  );
}
