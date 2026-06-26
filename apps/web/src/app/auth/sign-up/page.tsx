"use client";

import Link from "next/link";
import { useActionState } from "react";

import { Button } from "@/components/ui/Button";
import { controlClass, labelClass } from "@/components/ui/control";
import { cn } from "@/lib/cn";

import { signUpWithPassword, type AuthFormState } from "../actions";

const INITIAL: AuthFormState = { error: null };
const inputClass = cn(controlClass, "h-[34px] w-full px-sm");

export default function SignUpPage() {
  const [state, action, pending] = useActionState(signUpWithPassword, INITIAL);

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-md">
      <div className="w-full max-w-[26rem] rounded-md border border-line bg-panel p-lg shadow-sm">
        <h1 className="text-xl font-bold text-ink">Create your account</h1>
        <p className="mt-xs text-sm text-muted">
          Start planning trips in a couple of clicks.
        </p>

        <form action={action} className="mt-lg flex flex-col gap-sm">
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
              minLength={6}
              autoComplete="new-password"
              className={inputClass}
            />
          </label>
          {state.error ? (
            <p className="text-sm text-coral-ink">{state.error}</p>
          ) : null}
          {state.message ? (
            <p className="text-sm text-status-confirmed">{state.message}</p>
          ) : null}
          <Button type="submit" disabled={pending}>
            {pending ? "Creating…" : "Create account"}
          </Button>
        </form>

        <p className="mt-lg text-center text-sm text-muted">
          Already have an account?{" "}
          <Link href="/auth/login" className="font-bold text-ink underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
