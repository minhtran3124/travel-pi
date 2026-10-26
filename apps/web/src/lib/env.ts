// Next.js inlines `NEXT_PUBLIC_*` variables at build time by textually
// replacing literal `process.env.NEXT_PUBLIC_FOO` references. It does NOT
// inline dynamic bracket-indexed access in a loop, nor destructuring like
// `const { NEXT_PUBLIC_FOO } = process.env`. Reading these names in a loop
// would ship `undefined` to the browser. Do not "tidy" this into a loop —
// read each variable with literal property access, one line per variable.
const rawUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const rawPublishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

export function requireSupabaseEnv(): { url: string; key: string } {
  if (!rawUrl) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL is required at build time (Next.js inlines NEXT_PUBLIC_* during `next build`; it cannot be supplied later).",
    );
  }

  if (!rawPublishableKey) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY is required at build time (Next.js inlines NEXT_PUBLIC_* during `next build`; it cannot be supplied later).",
    );
  }

  return { url: rawUrl, key: rawPublishableKey };
}
