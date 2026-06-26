"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <EmptyState
        icon="⚠️"
        title="Something went wrong"
        hint="An unexpected error interrupted this page. You can try again."
        action={<Button onClick={() => reset()}>Try again</Button>}
      />
    </div>
  );
}
