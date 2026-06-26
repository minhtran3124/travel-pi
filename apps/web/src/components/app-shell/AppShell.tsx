"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

import { LocaleSwitcher } from "./LocaleSwitcher";

const NAV_LINKS = [
  { href: "/trips", key: "trips" },
  { href: "/places", key: "places" },
  { href: "/bookings", key: "bookings" },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const t = useTranslations("Nav");

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-line bg-panel">
        <nav className="mx-auto flex h-14 max-w-5xl items-center gap-xl px-xl">
          <Link
            href="/trips"
            className="flex items-center gap-sm text-base font-extrabold tracking-tight text-ink"
          >
            <span
              aria-hidden="true"
              className="grid size-7 place-items-center rounded-md bg-lime text-on-accent shadow-sm"
            >
              <PlaneMark />
            </span>
            {t("appName")}
          </Link>
          <ul className="flex items-center gap-lg">
            {NAV_LINKS.map(({ href, key }) => {
              const active =
                pathname === href || pathname.startsWith(`${href}/`);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "relative text-sm font-bold transition",
                      active ? "text-ink" : "text-muted hover:text-ink",
                    )}
                  >
                    {t(key)}
                    {active ? (
                      <span
                        aria-hidden="true"
                        className="absolute inset-x-0 -bottom-1.5 h-[2px] rounded-pill bg-lime"
                      />
                    ) : null}
                  </Link>
                </li>
              );
            })}
          </ul>
          <div className="ml-auto">
            <LocaleSwitcher />
          </div>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-xl py-xl">
        {children}
      </main>
    </div>
  );
}

/** Brand mark: a small paper plane, ink-on-lime in the wordmark badge. */
function PlaneMark() {
  return (
    <svg
      width={15}
      height={15}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinejoin="round"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M21 3 3 10.5l6.5 2.5L12 20l9-17Z" />
      <path d="M9.5 13 21 3" />
    </svg>
  );
}
