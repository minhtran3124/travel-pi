import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <EmptyState
        icon="🧭"
        title="Page not found"
        hint="The page you were looking for doesn't exist or has moved."
        action={
          <Link href="/trips">
            <Button>Back to Trips</Button>
          </Link>
        }
      />
    </div>
  );
}
