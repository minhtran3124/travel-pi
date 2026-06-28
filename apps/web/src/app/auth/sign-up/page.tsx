"use client";

import Link from "next/link";
import { useActionState } from "react";

import { AuthHero } from "@/components/auth/AuthHero";
import { OAuthButtons } from "@/components/auth/OAuthButtons";
import { Button } from "@/components/ui/Button";
import { controlClass, labelClass } from "@/components/ui/control";
import { cn } from "@/lib/cn";

import { signUpWithPassword, type AuthFormState } from "../actions";

const INITIAL: AuthFormState = { error: null };
const inputClass = cn(controlClass, "h-[38px] w-full px-md");

export default function SignUpPage() {
  const [state, action, pending] = useActionState(signUpWithPassword, INITIAL);

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
            Create your account
          </h1>
          <p className="mt-xs text-sm text-muted">
            A couple of details and you’re ready to plan your next trip.
          </p>

          {/* Success replaces the form once the confirmation email is sent. */}
          {state.message ? (
            <div
              role="status"
              className="mt-xl flex flex-col gap-sm rounded-md border border-line bg-status-confirmed/10 p-lg"
            >
              <span className="text-2xl" aria-hidden="true">
                📬
              </span>
              <p className="text-sm font-semibold text-status-confirmed">
                {state.message}
              </p>
              <p className="text-sm text-muted">
                Tap the link in the email to finish setting up your account.
              </p>
            </div>
          ) : (
            <form action={action} className="mt-xl flex flex-col gap-md">
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
              <label className="flex flex-col gap-xs">
                <span className={labelClass}>Password</span>
                <input
                  type="password"
                  name="password"
                  required
                  minLength={6}
                  autoComplete="new-password"
                  placeholder="At least 6 characters"
                  className={inputClass}
                />
              </label>

              {state.error ? (
                <p
                  role="alert"
                  className="rounded-sm bg-coral-soft px-md py-sm text-sm font-medium text-coral-ink"
                >
                  {state.error}
                </p>
              ) : null}

              <Button
                type="submit"
                disabled={pending}
                className="mt-xs h-[38px] w-full"
              >
                {pending ? "Creating…" : "Create account"}
              </Button>
            </form>
          )}

          <div className="my-lg flex items-center gap-sm text-faint">
            <span className="h-px flex-1 bg-line" />
            <span className="text-[0.7rem] font-semibold uppercase tracking-wide">
              or
            </span>
            <span className="h-px flex-1 bg-line" />
          </div>

          <OAuthButtons />

          <p className="mt-xl text-center text-sm text-muted">
            Already have an account?{" "}
            <Link
              href="/auth/login"
              className="font-bold text-ink underline decoration-lime decoration-2 underline-offset-2 hover:decoration-[3px]"
            >
              Sign in
            </Link>
          </p>
        </div>
      </main>
    </div>
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
