import { cn } from "@/lib/cn";

export interface MeterProps {
  /** Amount spent. */
  value: number;
  /** Cap to fill against; null/0 renders nothing (an uncapped category). */
  max: number | null | undefined;
  className?: string;
}

/**
 * A slim spent-vs-cap bar. Ink fill on a panel-raised track; once spend passes
 * the cap the fill saturates red (lime stays reserved for the active signal, so
 * budget progress is drawn in ink/red, never lime). Decorative only — the
 * adjacent figures carry the accessible value.
 */
export function Meter({ value, max, className }: MeterProps) {
  if (max === null || max === undefined || max <= 0) return null;
  const ratio = value / max;
  const over = ratio > 1;
  const pct = Math.max(0, Math.min(100, Math.round(ratio * 100)));
  return (
    <div
      aria-hidden="true"
      className={cn(
        "h-1.5 w-full overflow-hidden rounded-pill bg-panel-raised",
        className,
      )}
    >
      <div
        className={cn(
          "h-full rounded-pill transition-[width] duration-300 ease-out",
          over ? "bg-status-cancelled" : "bg-ink",
        )}
        style={{ width: `${over ? 100 : pct}%` }}
      />
    </div>
  );
}
