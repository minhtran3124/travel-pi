import { createClient } from "./client";

/**
 * Returns `{ Authorization: "Bearer <token>" }` when a Supabase session exists,
 * or `{}` when the user is logged out or running server-side.
 *
 * Fetches a fresh token on every call — never cache the return value across
 * requests as the token may have been silently refreshed by the SDK.
 */
export async function authHeader(): Promise<Record<string, string>> {
  if (typeof window === "undefined") return {};
  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}
