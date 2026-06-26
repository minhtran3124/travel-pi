import { cn } from "@/lib/cn";

export interface AgentAvatarProps {
  /** sm = transcript/header (24px), md = empty-state hero (40px). */
  size?: "sm" | "md";
  className?: string;
}

/**
 * The travel co-pilot's mark — a soft-lime disc with the assistant spark glyph.
 * Echoes the lime launcher so the agent has one consistent identity across the
 * launcher, the header, and every assistant turn (without spending the full-lime
 * "signal" budget — the disc is lime-soft, the launcher stays the one true lime).
 */
export function AgentAvatar({ size = "sm", className }: AgentAvatarProps) {
  const dim = size === "md" ? "h-10 w-10" : "h-6 w-6";
  const glyph = size === "md" ? 20 : 14;
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid shrink-0 place-items-center rounded-pill bg-lime-soft text-ink ring-1 ring-lime/50",
        dim,
        className,
      )}
    >
      <svg width={glyph} height={glyph} viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2l1.9 5.1L19 9l-5.1 1.9L12 16l-1.9-5.1L5 9l5.1-1.9L12 2zM18 14l.9 2.4L21.3 17l-2.4.9L18 20.3l-.9-2.4L14.7 17l2.4-.9L18 14z" />
      </svg>
    </span>
  );
}
