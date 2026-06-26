import type { CSSProperties, HTMLAttributes } from "react";

type StatusTone =
  | "confirmed"
  | "estimated"
  | "delayed"
  | "boarding"
  | "cancelled"
  | "hotel";

type TopicTone =
  | "transport"
  | "money"
  | "safety"
  | "culture"
  | "food"
  | "connectivity"
  | "health"
  | "etiquette"
  | "language"
  | "best_time";

export interface PillProps extends Omit<HTMLAttributes<HTMLSpanElement>, "color"> {
  variant: "status" | "topic";
  tone: StatusTone | TopicTone;
  label: string;
}

function colorVar(variant: "status" | "topic", tone: string): string {
  if (variant === "status") return `var(--color-status-${tone})`;
  if (tone === "best_time") return "var(--color-lime)";
  return `var(--color-topic-${tone})`;
}

export function Pill({ variant, tone, label, className, ...props }: PillProps) {
  const accent = colorVar(variant, tone);
  // Color is always paired with the text label; text is lightened over the
  // tinted background to hold AA contrast on the dark surface.
  const style: CSSProperties = {
    backgroundColor: `color-mix(in srgb, ${accent} 16%, transparent)`,
    color: `color-mix(in srgb, ${accent} 72%, white)`,
  };
  return (
    <span
      style={style}
      className={[
        "inline-flex items-center gap-xs rounded-pill px-sm py-px text-xs font-bold",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...props}
    >
      {label}
    </span>
  );
}
