"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { createClient } from "@/lib/supabase/server";

/** Result returned to form components via `useActionState`. */
export type AuthFormState = { error: string | null; message?: string };

export type OAuthProvider = "google" | "github";

/**
 * Sanitise the post-sign-in return path. Only same-origin absolute paths are
 * accepted — anything else (a protocol-relative `//host` or a full URL) would
 * turn the login form into an open redirect.
 */
function safeNext(value: FormDataEntryValue | null): string {
  const next = typeof value === "string" ? value : "";
  return next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

/** Absolute origin for building email redirect URLs from a Server Action. */
async function siteOrigin(): Promise<string> {
  const h = await headers();
  return (
    h.get("origin") ??
    process.env.NEXT_PUBLIC_SITE_URL ??
    "http://localhost:3000"
  );
}

export async function signInWithPassword(
  _prev: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const next = safeNext(formData.get("next"));

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return { error: error.message };

  revalidatePath("/", "layout");
  redirect(next);
}

export async function signUpWithPassword(
  _prev: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");

  const supabase = await createClient();
  const origin = await siteOrigin();
  const { error } = await supabase.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: `${origin}/auth/confirm` },
  });
  if (error) return { error: error.message };

  return { error: null, message: "Check your email to confirm your account." };
}

export async function signInWithMagicLink(
  _prev: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "");
  const next = safeNext(formData.get("next"));

  const supabase = await createClient();
  const origin = await siteOrigin();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: `${origin}/auth/confirm?next=${encodeURIComponent(next)}`,
    },
  });
  if (error) return { error: error.message };

  return { error: null, message: "Magic link sent — check your email." };
}

export async function signOut(): Promise<void> {
  const supabase = await createClient();
  await supabase.auth.signOut();
  revalidatePath("/", "layout");
  redirect("/auth/login");
}

export async function signInWithOAuth(
  provider: OAuthProvider,
): Promise<AuthFormState> {
  // DEFERRED (specs/supabase-auth): Google/GitHub providers are not yet
  // configured in the Supabase dashboard (client id/secret + redirect URLs).
  // The flow is scaffolded but guarded off until that setup is done, so we
  // never start a half-working redirect.
  return {
    error: `${provider} sign-in is not enabled yet — configure the provider in Supabase first.`,
  };
}
