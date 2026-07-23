import { cn } from "@/lib/cn";

export interface AgentAvatarProps {
  /** sm = transcript/header (24px), md = empty-state hero (40px). */
  size?: "sm" | "md";
  className?: string;
}

/**
 * Tin's mark — a soft-lime disc with a bold "T" monogram. Echoes the lime
 * launcher so the agent has one consistent identity across the launcher, the
 * header, and every assistant turn (without spending the full-lime "signal"
 * budget — the disc is lime-soft, the launcher stays the one true lime).
 */
export function AgentAvatar({ size = "sm", className }: AgentAvatarProps) {
  const dim = size === "md" ? "h-10 w-10" : "h-6 w-6";
  const text = size === "md" ? "text-base" : "text-xs";
  return (
    <span
      role="img"
      aria-label="Tin"
      className={cn(
        "grid shrink-0 place-items-center rounded-pill bg-lime-soft text-ink ring-1 ring-lime/50",
        dim,
        className,
      )}
    >
      <span className={cn("font-semibold leading-none", text)}>T</span>
    </span>
  );
}
