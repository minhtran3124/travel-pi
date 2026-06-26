"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

const NAV_LINKS = [
  { href: "/trips", label: "Trips" },
  { href: "/places", label: "Places" },
  { href: "/bookings", label: "Bookings" },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-line bg-panel">
        <nav className="mx-auto flex h-14 max-w-5xl items-center gap-xl px-xl">
          <Link
            href="/trips"
            className="text-base font-extrabold tracking-tight text-ink"
          >
            Travel Planner
          </Link>
          <ul className="flex items-center gap-lg">
            {NAV_LINKS.map(({ href, label }) => {
              const active =
                pathname === href || pathname.startsWith(`${href}/`);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "text-sm font-bold transition",
                      active
                        ? "text-ink"
                        : "text-muted hover:text-ink",
                    )}
                  >
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-xl py-xl">
        {children}
      </main>
    </div>
  );
}
