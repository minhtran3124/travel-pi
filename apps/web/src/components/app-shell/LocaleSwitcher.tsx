"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { locales, type Locale } from "@/i18n/config";
import { setUserLocale } from "@/i18n/locale";
import { cn } from "@/lib/cn";

/**
 * Cookie-based locale switcher (no URL routing). Writing the cookie is a server
 * action; `router.refresh()` re-renders the server tree with the new locale.
 */
export function LocaleSwitcher() {
  const t = useTranslations("LocaleSwitcher");
  const locale = useLocale();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  function onChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const next = event.target.value as Locale;
    startTransition(async () => {
      await setUserLocale(next);
      router.refresh();
    });
  }

  return (
    <label className="relative inline-flex items-center">
      <span className="sr-only">{t("label")}</span>
      <GlobeMark className="pointer-events-none absolute left-2.5 size-3.5 text-muted" />
      <select
        value={locale}
        onChange={onChange}
        disabled={isPending}
        aria-label={t("label")}
        className={cn(
          "appearance-none rounded-pill border border-line bg-panel-raised",
          "py-1.5 pl-7 pr-7 text-xs font-bold uppercase tracking-wide text-ink",
          "cursor-pointer transition-colors hover:border-ink hover:bg-panel",
          // Focus uses the global neutral ring (globals.css `*:focus-visible`);
          // the lime accent is never the focus color (DESIGN.md §Inputs).
          isPending && "cursor-wait opacity-60",
        )}
      >
        {locales.map((cur) => (
          <option key={cur} value={cur}>
            {cur.toUpperCase()}
          </option>
        ))}
      </select>
      <ChevronMark className="pointer-events-none absolute right-2.5 size-3 text-muted" />
    </label>
  );
}

function GlobeMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18Z" />
    </svg>
  );
}

function ChevronMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}
