import { type EmailOtpType } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

import { safeNextPath } from "@/lib/auth/next-path";
import { createClient } from "@/lib/supabase/server";

/**
 * Email OTP confirmation: magic-link and signup-confirmation emails redirect
 * here with `token_hash` + `type`. Verify the OTP to establish the session,
 * then forward to `next` (default `/`). On failure, route to the auth error
 * page.
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const token_hash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  // Resolved against this origin, never concatenated onto it: a raw
  // `@evil.example` would otherwise slide the host into the userinfo slot.
  const next = safeNextPath(searchParams.get("next"), origin);

  if (token_hash && type) {
    const supabase = await createClient();
    const { error } = await supabase.auth.verifyOtp({ type, token_hash });
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  return NextResponse.redirect(`${origin}/auth/auth-code-error`);
}
