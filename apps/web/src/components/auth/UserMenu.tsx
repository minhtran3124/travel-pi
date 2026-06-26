"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { signOut } from "@/app/auth/actions";
import { cn } from "@/lib/cn";
import { createClient } from "@/lib/supabase/client";

/**
 * Top-bar account control. Reflects the live Supabase auth state:
 * - resolving → renders nothing (avoids a sign-in/avatar flicker on load)
 * - signed out → a quiet "Sign in" link
 * - signed in → an avatar badge (initial + name) that opens a menu with the
 *   full email and a Sign out action.
 *
 * Subscribes to `onAuthStateChange`, so it updates the moment the user signs in
 * or out without a full reload.
 */
export function UserMenu() {
  // undefined = still resolving; null = signed out; string = signed-in email.
  const [email, setEmail] = useState<string | null | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth
      .getUser()
      .then(({ data }) => setEmail(data.user?.email ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user?.email ?? null);
      setOpen(false);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!open) return;
    function onDoc(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (email === undefined) return null;

  if (!email) {
    return (
      <Link
        href="/auth/login"
        className="text-sm font-bold text-muted transition hover:text-ink"
      >
        Sign in
      </Link>
    );
  }

  const initial = email[0]?.toUpperCase() ?? "?";
  const name = email.split("@")[0];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-sm rounded-pill border border-line bg-panel py-px pl-px pr-sm transition hover:bg-panel-raised"
      >
        <Avatar initial={initial} className="size-7 text-xs" />
        <span className="hidden max-w-[12ch] truncate text-sm font-semibold text-ink sm:inline">
          {name}
        </span>
        <ChevronDown
          className={cn(
            "hidden shrink-0 text-muted transition-transform sm:block",
            open && "rotate-180",
          )}
        />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-sm w-[15rem] overflow-hidden rounded-md border border-line bg-panel shadow-lift"
        >
          <div className="flex items-center gap-sm border-b border-line px-md py-sm">
            <Avatar initial={initial} className="size-8 text-sm" />
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold text-ink">
                {name}
              </span>
              <span className="block truncate text-xs text-muted">{email}</span>
            </span>
          </div>
          <form action={signOut}>
            <button
              type="submit"
              role="menuitem"
              className="flex w-full items-center gap-sm px-md py-sm text-left text-sm font-medium text-ink transition hover:bg-panel-raised"
            >
              <LogoutIcon />
              Sign out
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}

function Avatar({
  initial,
  className,
}: {
  initial: string;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid shrink-0 place-items-center rounded-pill bg-ink font-bold text-white",
        className,
      )}
    >
      {initial}
    </span>
  );
}

function ChevronDown({ className }: { className?: string }) {
  return (
    <svg
      width={14}
      height={14}
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

function LogoutIcon() {
  return (
    <svg
      width={15}
      height={15}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0 text-muted"
    >
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
    </svg>
  );
}
