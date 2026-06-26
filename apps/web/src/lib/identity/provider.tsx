"use client";

import { createContext, useEffect, useState, type ReactNode } from "react";

import { setUserId } from "@/lib/api/client";

const STORAGE_KEY = "travel.userId";

// The single auth seam: a local pseudo-identity. Swappable for real auth later
// (replace the localStorage read with a session lookup) without touching callers.
export const IdentityContext = createContext<string | null>(null);

/**
 * Establishes the local pseudo-identity for this browser.
 *
 * On mount it reads `localStorage["travel.userId"]`, generating and persisting a
 * UUID if absent, then publishes it through context AND to the React-free API
 * client via `setUserId` (so the request middleware can attach `X-User-Id`).
 *
 * Hydration: the id starts as `null` and is only set inside the mount effect.
 * The server has no localStorage, so rendering `null` on both server and the
 * first client tick avoids a hydration mismatch; the real id appears on the
 * effect-driven re-render.
 */
export function IdentityProvider({ children }: { children: ReactNode }) {
  const [userId, setUserIdState] = useState<string | null>(null);

  useEffect(() => {
    let id = localStorage.getItem(STORAGE_KEY);
    if (id === null) {
      id = crypto.randomUUID();
      localStorage.setItem(STORAGE_KEY, id);
    }
    // Intentional client-only state set: localStorage is unavailable during SSR,
    // so the id can only be resolved post-mount. This drives the single
    // hydration-safe re-render from `null` to the real id.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUserIdState(id);
    setUserId(id);
  }, []);

  return (
    <IdentityContext.Provider value={userId}>
      {children}
    </IdentityContext.Provider>
  );
}
