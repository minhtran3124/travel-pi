import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";

export default async function NotFound() {
  const t = await getTranslations("Errors");

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <EmptyState
        icon="🧭"
        title={t("notFoundTitle")}
        hint={t("notFoundHint")}
        action={
          <Link href="/trips">
            <Button>{t("backToTrips")}</Button>
          </Link>
        }
      />
    </div>
  );
}
