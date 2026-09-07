import { NextResponse } from "next/server";

import { safeNextPath } from "@/lib/auth/next-path";
import { createClient } from "@/lib/supabase/server";

/**
 * OAuth / PKCE callback: Supabase redirects here with `?code=...`. Exchange the
 * code for a session cookie, then send the user on to `next` (default `/`).
 * On any failure, route to the shared auth error page.
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  // Resolved against this origin, never concatenated onto it: a raw
  // `@evil.example` would otherwise slide the host into the userinfo slot.
  const next = safeNextPath(searchParams.get("next"), origin);

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  return NextResponse.redirect(`${origin}/auth/auth-code-error`);
}
