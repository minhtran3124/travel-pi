/**
 * Whether trip research is available. Mirrors the API's `research_enabled` kill
 * switch, which drops the research router entirely when off: set
 * `NEXT_PUBLIC_RESEARCH_ENABLED=false` alongside `RESEARCH_ENABLED=false` so the
 * trip page hides a tab whose Start button could only 404. On by default, as the
 * API is.
 */
export function researchEnabled(): boolean {
  return process.env.NEXT_PUBLIC_RESEARCH_ENABLED !== "false";
}
