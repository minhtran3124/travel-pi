"use client";

import { Button } from "@/components/ui/Button";

/**
 * Google / GitHub sign-in buttons.
 *
 * DEFERRED (specs/supabase-auth): the providers are not yet configured in the
 * Supabase dashboard (client id/secret + redirect URLs), so the buttons render
 * disabled — the UI is in place without exposing a half-working flow.
 */
export function OAuthButtons() {
  return (
    <div className="flex flex-col gap-sm">
      <Button
        variant="ghost"
        disabled
        title="Configure Google in Supabase to enable"
      >
        Continue with Google
      </Button>
      <Button
        variant="ghost"
        disabled
        title="Configure GitHub in Supabase to enable"
      >
        Continue with GitHub
      </Button>
      <p className="text-center text-[0.7rem] text-faint">
        Social sign-in is coming soon.
      </p>
    </div>
  );
}
