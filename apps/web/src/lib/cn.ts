/**
 * Join class-name fragments, dropping falsy values. The project-wide replacement
 * for the hand-rolled `[...].filter(Boolean).join(" ")` pattern.
 */
export function cn(
  ...parts: Array<string | false | null | undefined>
): string {
  return parts.filter(Boolean).join(" ");
}
