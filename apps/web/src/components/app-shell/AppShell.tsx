"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useState } from "react";

import { cn } from "@/lib/cn";

import { UserMenu } from "@/components/auth/UserMenu";
import { ThemeToggle } from "@/components/theme/ThemeToggle";

import { LocaleSwitcher } from "./LocaleSwitcher";

const NAV_LINKS = [
  { href: "/trips", key: "trips" },
  { href: "/places", key: "places" },
  { href: "/flights", key: "flights" },
  { href: "/hotels", key: "hotels" },
  { href: "/bookings", key: "bookings" },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const t = useTranslations("Nav");
  const [menuOpen, setMenuOpen] = useState(false);

  // Auth screens are standalone surfaces — no app nav/chrome around them.
  if (pathname?.startsWith("/auth")) {
    return <>{children}</>;
  }

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

          {/* Desktop nav */}
          <ul className="hidden items-center gap-lg sm:flex">
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

          <div className="ml-auto flex items-center gap-sm">
            <div className="hidden sm:block">
              <LocaleSwitcher />
            </div>
            <ThemeToggle />
            <UserMenu />
            {/* Mobile hamburger */}
            <button
              type="button"
              aria-label={menuOpen ? t("menuClose") : t("menuOpen")}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((o) => !o)}
              className="grid size-8 place-items-center rounded-md text-ink transition hover:bg-panel-raised sm:hidden"
            >
              {menuOpen ? <CloseIcon /> : <HamburgerIcon />}
            </button>
          </div>
        </nav>

        {/* Mobile dropdown */}
        {menuOpen && (
          <div className="border-t border-line bg-panel px-xl py-md sm:hidden">
            <ul className="flex flex-col gap-sm">
              {NAV_LINKS.map(({ href, key }) => {
                const active =
                  pathname === href || pathname.startsWith(`${href}/`);
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      onClick={() => setMenuOpen(false)}
                      className={cn(
                        "block rounded-md px-sm py-xs text-sm font-bold transition",
                        active
                          ? "bg-panel-raised text-ink"
                          : "text-muted hover:bg-panel-raised hover:text-ink",
                      )}
                    >
                      {t(key)}
                    </Link>
                  </li>
                );
              })}
            </ul>
            <div className="mt-md border-t border-line pt-md">
              <LocaleSwitcher />
            </div>
          </div>
        )}
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-xl py-xl">
        {children}
      </main>
    </div>
  );
}

function HamburgerIcon() {
  return (
    <svg width={18} height={18} viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" aria-hidden="true">
      <path d="M2 4.5h14M2 9h14M2 13.5h14" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width={18} height={18} viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" aria-hidden="true">
      <path d="M3 3l12 12M15 3L3 15" />
    </svg>
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
