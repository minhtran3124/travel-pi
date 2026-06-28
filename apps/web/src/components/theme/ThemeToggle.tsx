"use client";

import { useTheme } from "next-themes";
import { useTranslations } from "next-intl";
import { useSyncExternalStore } from "react";

import { cn } from "@/lib/cn";

/** True only after client hydration — without setState-in-effect (server
 * snapshot is `false`, client snapshot is `true`). Lets us defer theme-dependent
 * rendering past first paint to avoid a hydration mismatch. */
const emptySubscribe = () => () => {};
function useMounted() {
  return useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );
}

/**
 * Light/dark toggle. `next-themes` resolves the active theme only on the
 * client, so we gate rendering behind a `mounted` flag and show a same-size
 * placeholder during SSR/first paint to avoid hydration mismatch + layout shift.
 */
export function ThemeToggle() {
  const t = useTranslations("ThemeToggle");
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();

  const buttonClasses = cn(
    "inline-grid size-8 place-items-center rounded-pill border border-line",
    "bg-panel-raised text-ink transition-colors hover:border-ink hover:bg-panel",
    // Focus uses the global neutral ring (globals.css `*:focus-visible`); no
    // custom ring/box-shadow here (DESIGN.md §Inputs).
  );

  if (!mounted) {
    // Non-interactive placeholder, identical footprint, hidden from a11y tree.
    return <div aria-hidden="true" className={buttonClasses} />;
  }

  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={t("toggle")}
      aria-pressed={isDark}
      className={buttonClasses}
    >
      {isDark ? <SunMark className="size-4" /> : <MoonMark className="size-4" />}
    </button>
  );
}

function SunMark({ className }: { className?: string }) {
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
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  );
}

function MoonMark({ className }: { className?: string }) {
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
      <path d="M21 12.79A9 9 0 1 1 11.21 3a7 7 0 0 0 9.79 9.79Z" />
    </svg>
  );
}
