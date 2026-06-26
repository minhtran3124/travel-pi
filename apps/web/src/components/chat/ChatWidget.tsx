"use client";

import { useQueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";

import { qk } from "@/lib/api/keys";
import { ChatLauncher } from "./ChatLauncher";
import { ChatPanel } from "./ChatPanel";
import { useAgentStream } from "./useAgentStream";

/** Extract a trip id from a `/trips/{id}` route, else undefined. */
function tripIdFromPath(pathname: string | null): string | undefined {
  if (!pathname) return undefined;
  const match = pathname.match(/^\/trips\/([^/]+)/);
  return match?.[1];
}

/**
 * Kith-style agent co-pilot. Composes the launcher FAB + chat panel, manages
 * open state, derives the active trip from the route, and refreshes the
 * planner's trip queries once an assistant turn completes (the agent may have
 * mutated trip data server-side).
 */
export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const tripId = tripIdFromPath(pathname);
  const queryClient = useQueryClient();

  const onTurnComplete = useCallback(() => {
    if (!tripId) return;
    queryClient.invalidateQueries({ queryKey: qk.trip(tripId) });
    queryClient.invalidateQueries({ queryKey: qk.items(tripId) });
    queryClient.invalidateQueries({ queryKey: qk.budget(tripId) });
    queryClient.invalidateQueries({ queryKey: qk.expenses(tripId) });
  }, [queryClient, tripId]);

  const stream = useAgentStream({ tripId, onTurnComplete });

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-md">
      {open ? (
        <ChatPanel stream={stream} onClose={() => setOpen(false)} />
      ) : null}
      <ChatLauncher open={open} onToggle={() => setOpen((v) => !v)} />
    </div>
  );
}
