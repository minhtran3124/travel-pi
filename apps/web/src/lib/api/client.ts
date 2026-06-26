import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";

// --- Identity seam -----------------------------------------------------------
// The FE's own ownership marker for REST calls. The agent `user_id` travels in
// the request BODY (set by callers); this is a separate `X-User-Id` header the
// BE uses to scope REST resource ownership.
//
// Kept React-free on purpose: this is the only BE-aware layer. Task 1.3's
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

// --- SSE base URL ------------------------------------------------------------
// Direct-to-origin base for Server-Sent Events (used later by the chat widget),
// which bypass the `/api/be` rewrite and hit the agent backend directly.
export function streamBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}
