import { requireSupabaseEnv } from "@/lib/env";

// Next.js calls `register()` once, on server startup. Validating the Supabase
// env vars here makes a deploy built or promoted without them fail loudly at
// boot instead of returning a 500 on every user request.
//
// What this CANNOT do: a client bundle built without these variables already
// has `undefined` inlined by `next build` (Next.js inlines `NEXT_PUBLIC_*` at
// build time) — nothing at runtime can recover that. This guards the server
// half only.
export function register() {
  requireSupabaseEnv();
}
