import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";

// --- Identity seam -----------------------------------------------------------
// The FE's own ownership marker for REST calls. The agent `user_id` travels in
// the request BODY (set by callers); this is a separate `X-User-Id` header that
// is reserved for scoping REST resource ownership once real auth lands.
//
// NOTE: the current mock BE ignores `X-User-Id` entirely (no auth), so the
// known "first query may fire before IdentityProvider's mount effect sets the
// id" race is a no-op today. When the BE starts scoping on this header, gate
// identity-dependent queries on a non-null id (e.g. `enabled: !!userId`).
//
// Kept React-free on purpose: this is the only BE-aware layer. The
// IdentityProvider imports `setUserId` and calls it on mount/identity change.
let currentUserId: string | null = null;

export function setUserId(id: string | null): void {
  currentUserId = id;
}

export function getUserId(): string | null {
  return currentUserId;
}

// --- Idempotency-Key targeting ----------------------------------------------
// Only `POST /trips` and `POST /trips/{trip_id}/items` are mutation-creating
// endpoints that need client-generated idempotency keys. Match on the templated
// schema path so concrete ids (e.g. /trips/abc-123/items) are handled uniformly.
const IDEMPOTENT_POST_PATHS = new Set<string>([
  "/trips",
  "/trips/{trip_id}/items",
]);

const identityMiddleware: Middleware = {
  onRequest({ request, schemaPath }) {
    const userId = getUserId();
    if (userId !== null) {
      request.headers.set("X-User-Id", userId);
    }

    if (request.method === "POST" && IDEMPOTENT_POST_PATHS.has(schemaPath)) {
      request.headers.set("Idempotency-Key", crypto.randomUUID());
    }

    return request;
  },
};

export const client = createClient<paths>({ baseUrl: "/api/be" });
client.use(identityMiddleware);

// --- Response unwrapping ------------------------------------------------------
/**
 * Await an openapi-fetch call, throw its `error` if present, and return `data`.
 * Collapses the repeated `const { data, error } = await ...; if (error) throw
 * error; return data;` block at every query/mutation call site.
 *
 * For DELETEs (or any call with no response body) the resolved value is
 * `undefined`; callers that ignore the return value are unaffected.
 */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown }>,
): Promise<T> {
  const { data, error } = await call;
  if (error) throw error;
  return data as T;
}

// --- SSE base URL ------------------------------------------------------------
// Direct-to-origin base for Server-Sent Events (used later by the chat widget),
// which bypass the `/api/be` rewrite and hit the agent backend directly.
export function streamBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}
