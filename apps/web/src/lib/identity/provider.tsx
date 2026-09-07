"use client";

import { createContext, useEffect, useState, type ReactNode } from "react";

import { createClient } from "@/lib/supabase/client";

/** Where the browser stands with respect to a Supabase session. */
export type IdentityStatus = "loading" | "signed-out" | "signed-in";

export interface Identity {
  /** The authenticated Supabase user id, or `null` while loading / signed out. */
  userId: string | null;
  status: IdentityStatus;
}

// The single auth seam. Identity now derives from the Supabase session — there
// is no anonymous pseudo-identity. `status` starts as `loading` until the first
// session lookup resolves, then tracks sign-in/out live.
export const IdentityContext = createContext<Identity>({
  userId: null,
  status: "loading",
});

/**
 * Publishes the Supabase session identity through context.
 *
 * On mount it resolves the current session and then subscribes to
 * `onAuthStateChange`, so sign-in/sign-out (in this tab or another) updates
 * `{ userId, status }` live. When signed out, `userId` is `null` and `status`
 * is `signed-out`; consumers gate authed work on `status === "signed-in"`.
 *
 * Hydration: the server has no session, so both the server render and the first
 * client tick see `status: "loading"` / `userId: null`, avoiding a mismatch; the
 * real identity appears on the effect-driven re-render.
 */
export function IdentityProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity>({
    userId: null,
    status: "loading",
  });

  useEffect(() => {
    const supabase = createClient();
    let active = true;

    const publish = (userId: string | null) =>
      setIdentity(
        userId
          ? { userId, status: "signed-in" }
          : { userId: null, status: "signed-out" },
      );

    void supabase.auth.getSession().then(({ data }) => {
      if (active) publish(data.session?.user.id ?? null);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      publish(session?.user.id ?? null);
    });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  return (
    <IdentityContext.Provider value={identity}>
      {children}
    </IdentityContext.Provider>
  );
}
