"use client";

import { signOut } from "@/app/auth/actions";
import { Button } from "@/components/ui/Button";

/** Submits the signOut server action, which clears the session and redirects. */
export function SignOutButton() {
  return (
    <form action={signOut}>
      <Button type="submit" variant="ghost">
        Sign out
      </Button>
    </form>
  );
}
