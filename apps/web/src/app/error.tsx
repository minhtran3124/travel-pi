"use client";

import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("Errors");

  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <EmptyState
        icon="⚠️"
        title={t("somethingWentWrongTitle")}
        hint={t("somethingWentWrongHint")}
        action={<Button onClick={() => reset()}>{t("tryAgain")}</Button>}
      />
    </div>
  );
}
