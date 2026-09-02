"use client";

import { useContext } from "react";

import { IdentityContext, type Identity } from "./provider";

/**
 * Returns the full identity `{ userId, status }` from {@link IdentityProvider}.
 * Consumers that need to distinguish "loading" from "signed-out" read `status`.
 */
export function useIdentity(): Identity {
  return useContext(IdentityContext);
}

/**
 * Returns the current Supabase user id, or `null` while the session is loading
 * or the user is signed out. Convenience wrapper over {@link useIdentity}.
 */
export function useUserId(): string | null {
  return useContext(IdentityContext).userId;
}
