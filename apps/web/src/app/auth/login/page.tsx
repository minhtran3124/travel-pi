"use client";

import Link from "next/link";
import { use, useActionState, useState } from "react";

import { AuthHero } from "@/components/auth/AuthHero";
import { OAuthButtons } from "@/components/auth/OAuthButtons";
import { Button } from "@/components/ui/Button";
import { controlClass, labelClass } from "@/components/ui/control";
import { cn } from "@/lib/cn";

import {
  signInWithMagicLink,
  signInWithPassword,
  type AuthFormState,
} from "../actions";

const INITIAL: AuthFormState = { error: null };
const inputClass = cn(controlClass, "h-[38px] w-full px-md");

type Mode = "password" | "magic";

export default function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  // Where the middleware bounced the visitor from — echoed back to the server
  // action as a hidden field, which re-validates it before redirecting.
  const { next } = use(searchParams);
  const [mode, setMode] = useState<Mode>("password");
  const [pwState, pwAction, pwPending] = useActionState(
    signInWithPassword,
    INITIAL,
  );
  const [linkState, linkAction, linkPending] = useActionState(
    signInWithMagicLink,
    INITIAL,
  );

  const isPassword = mode === "password";
  const action = isPassword ? pwAction : linkAction;
  const state = isPassword ? pwState : linkState;
  const pending = isPassword ? pwPending : linkPending;

  return (
    <div className="grid min-h-[100dvh] lg:grid-cols-[1.04fr_1fr]">
      <AuthHero />

      <main className="flex items-center justify-center px-lg py-xl sm:px-xl">
        <div className="w-full max-w-[25rem]">
          {/* Compact wordmark — only on mobile, where the hero is hidden. */}
          <div className="mb-xl flex items-center gap-sm text-base font-extrabold tracking-tight text-ink lg:hidden">
            <span className="grid size-7 place-items-center rounded-md bg-lime text-on-accent shadow-sm">
              <PaperPlane />
            </span>
            Travel Planner
          </div>

          <h1 className="text-[1.6rem] font-extrabold leading-tight tracking-tight text-ink">
            Welcome back
          </h1>
          <p className="mt-xs text-sm text-muted">
            Good to see you — let’s get you back to your trips.
          </p>

          {/* Method toggle — borrows the app's lime-underline tab language. */}
          <div
            role="tablist"
            aria-label="Sign-in method"
            className="mt-xl flex gap-xl border-b border-line"
          >
            <MethodTab
              active={isPassword}
              onClick={() => setMode("password")}
            >
              Password
            </MethodTab>
            <MethodTab active={!isPassword} onClick={() => setMode("magic")}>
              Magic link
            </MethodTab>
          </div>

          <form action={action} className="mt-lg flex flex-col gap-md">
            <input type="hidden" name="next" value={next ?? "/"} />

            <label className="flex flex-col gap-xs">
              <span className={labelClass}>Email</span>
              <input
                type="email"
                name="email"
                required
                autoComplete="email"
                placeholder="you@example.com"
                className={inputClass}
              />
            </label>

            {isPassword ? (
              <label className="flex flex-col gap-xs">
                <span className={labelClass}>Password</span>
                <input
                  type="password"
                  name="password"
                  required
                  autoComplete="current-password"
                  placeholder="••••••••"
                  className={inputClass}
                />
              </label>
            ) : (
              <p className="text-xs leading-relaxed text-muted">
                No password needed — we’ll email you a one-tap link to sign in.
              </p>
            )}

            {state.error ? (
              <p
                role="alert"
                className="rounded-sm bg-coral-soft px-md py-sm text-sm font-medium text-coral-ink"
              >
                {state.error}
              </p>
            ) : null}
            {state.message ? (
              <p
                role="status"
                className="rounded-sm bg-status-confirmed/10 px-md py-sm text-sm font-medium text-status-confirmed"
              >
                {state.message}
              </p>
            ) : null}

            <Button
              type="submit"
              disabled={pending}
              className="mt-xs h-[38px] w-full"
            >
              {pending
                ? isPassword
                  ? "Signing in…"
                  : "Sending…"
                : isPassword
                  ? "Sign in"
                  : "Email me a magic link"}
            </Button>
          </form>

          <div className="my-lg flex items-center gap-sm text-faint">
            <span className="h-px flex-1 bg-line" />
            <span className="text-[0.7rem] font-semibold uppercase tracking-wide">
              or
            </span>
            <span className="h-px flex-1 bg-line" />
          </div>

          <OAuthButtons />

          <p className="mt-xl text-center text-sm text-muted">
            New here?{" "}
            <Link
              href={
                next && next !== "/"
                  ? `/auth/sign-up?next=${encodeURIComponent(next)}`
                  : "/auth/sign-up"
              }
              className="font-bold text-ink underline decoration-lime decoration-2 underline-offset-2 hover:decoration-[3px]"
            >
              Create an account
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}

function MethodTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "relative -mb-px pb-sm text-sm font-bold transition-colors",
        active ? "text-ink" : "text-muted hover:text-ink",
      )}
    >
      {children}
      {active ? (
        <span
          aria-hidden="true"
          className="absolute inset-x-0 bottom-0 h-[2px] rounded-pill bg-lime"
        />
      ) : null}
    </button>
  );
}

function PaperPlane() {
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
