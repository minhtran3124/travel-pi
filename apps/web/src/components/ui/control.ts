// Shared styling tokens for labelled form controls (Field / Select / Textarea),
// so the label treatment and control chrome live in one place instead of being
// copy-pasted per form.

/** The small uppercase caption above every control. */
export const labelClass =
  "text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted";

/**
 * Border / background / text chrome shared by inputs, selects, and textareas.
 * Carries the full interactive state set DESIGN.md requires: a hairline `line`
 * border that hardens on hover (mirroring the card hover language), the global
 * neutral focus ring (globals.css `*:focus-visible`), and a dimmed disabled
 * state. The OS-native widget chrome is stripped in globals.css.
 */
export const controlClass =
  "rounded-sm border border-line bg-panel-raised text-sm text-ink placeholder:text-muted transition-colors hover:border-[#e0e0e0] disabled:cursor-not-allowed disabled:opacity-50";
