import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";

export default function AuthCodeErrorPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <EmptyState
        icon="🔐"
        title="Sign-in link didn’t work"
        hint="The link may have expired or already been used. Request a new one and try again."
        action={
          <Link href="/auth/login">
            <Button>Back to sign in</Button>
          </Link>
        }
      />
    </div>
  );
}
