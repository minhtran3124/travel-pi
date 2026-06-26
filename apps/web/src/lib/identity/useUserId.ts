"use client";

import { useContext } from "react";

import { IdentityContext } from "./provider";

/**
 * Returns the current local pseudo-identity id, or `null` during the first
 * SSR/hydration tick before {@link IdentityProvider}'s mount effect runs.
 */
export function useUserId(): string | null {
  return useContext(IdentityContext);
}
