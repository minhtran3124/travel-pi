"use client";

import Link from "next/link";
import { useActionState } from "react";

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
const inputClass = cn(controlClass, "h-[34px] w-full px-sm");

export default function LoginPage() {
  const [pwState, pwAction, pwPending] = useActionState(
    signInWithPassword,
    INITIAL,
  );
  const [linkState, linkAction, linkPending] = useActionState(
    signInWithMagicLink,
    INITIAL,
  );

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-md">
      <div className="w-full max-w-[26rem] rounded-md border border-line bg-panel p-lg shadow-sm">
        <h1 className="text-xl font-bold text-ink">Welcome back</h1>
        <p className="mt-xs text-sm text-muted">
          Sign in to plan and track your trips.
        </p>

        <form action={pwAction} className="mt-lg flex flex-col gap-sm">
          <label className="flex flex-col gap-xs">
            <span className={labelClass}>Email</span>
            <input
              type="email"
              name="email"
              required
              autoComplete="email"
              className={inputClass}
            />
          </label>
          <label className="flex flex-col gap-xs">
            <span className={labelClass}>Password</span>
            <input
              type="password"
              name="password"
              required
              autoComplete="current-password"
              className={inputClass}
            />
          </label>
          {pwState.error ? (
            <p className="text-sm text-coral-ink">{pwState.error}</p>
          ) : null}
          <Button type="submit" disabled={pwPending}>
            {pwPending ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <div className="my-md flex items-center gap-sm text-faint">
          <span className="h-px flex-1 bg-line" />
          <span className="text-[0.7rem] uppercase tracking-wide">or</span>
          <span className="h-px flex-1 bg-line" />
        </div>

        <form action={linkAction} className="flex flex-col gap-sm">
          <label className="flex flex-col gap-xs">
            <span className={labelClass}>Email a magic link</span>
            <input
              type="email"
              name="email"
              required
              autoComplete="email"
              className={inputClass}
            />
          </label>
          {linkState.error ? (
            <p className="text-sm text-coral-ink">{linkState.error}</p>
          ) : null}
          {linkState.message ? (
            <p className="text-sm text-status-confirmed">{linkState.message}</p>
          ) : null}
          <Button type="submit" variant="ghost" disabled={linkPending}>
            {linkPending ? "Sending…" : "Send magic link"}
          </Button>
        </form>

        <div className="mt-md">
          <OAuthButtons />
        </div>

        <p className="mt-lg text-center text-sm text-muted">
          New here?{" "}
          <Link href="/auth/sign-up" className="font-bold text-ink underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
