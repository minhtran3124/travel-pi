"use client";

import { Pill } from "@/components/ui/Pill";
import { cn } from "@/lib/cn";
import type { TripItem, TripItemKind, TripItemStatus } from "@/lib/query/items";

const KIND_ICON: Record<TripItemKind, string> = {
  place: "📍",
  activity: "🎒",
  meal: "🍽️",
  transport: "🚆",
  note: "📝",
};

// Map the planning status onto the closed Pill status spectrum (no new hues).
const STATUS_TONE: Record<
  TripItemStatus,
  "confirmed" | "estimated" | "delayed" | "boarding"
> = {
  booked: "confirmed",
  pending: "estimated",
  constraint: "delayed",
  optional: "boarding",
};

export interface ItemRowProps {
  item: TripItem;
  canMoveUp: boolean;
  canMoveDown: boolean;
  busy?: boolean;
  /** Today's day — the timeline node lights up with the active lime signal. */
  highlight?: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

function iconButtonClass(): string {
  return "inline-flex size-7 items-center justify-center rounded-sm border border-transparent bg-transparent text-sm text-muted transition hover:border-line hover:bg-panel hover:text-ink disabled:cursor-not-allowed disabled:opacity-40";
}

export function ItemRow({
  item,
  canMoveUp,
  canMoveDown,
  busy = false,
  highlight = false,
  onMoveUp,
  onMoveDown,
  onEdit,
  onDelete,
}: ItemRowProps) {
  return (
    <li className="relative flex gap-md">
      {/* Timeline node — the kind glyph doubles as the marker on the day rail. */}
      <span
        aria-hidden="true"
        className={cn(
          "relative z-10 mt-1 grid size-8 shrink-0 place-items-center rounded-pill text-base shadow-card",
          highlight ? "bg-lime-soft ring-2 ring-lime" : "bg-panel ring-1 ring-line",
        )}
      >
        {KIND_ICON[item.kind]}
      </span>

      <div className="group flex min-w-0 flex-1 items-start gap-md rounded-md border border-line-soft bg-panel-raised p-md transition hover:border-line">
        <div className="flex min-w-0 flex-1 flex-col gap-xs">
          <div className="flex flex-wrap items-center gap-sm">
            {item.start_time ? (
              <span className="font-mono text-xs font-bold tabular-nums text-muted">
                {item.start_time}
              </span>
            ) : null}
            <span className="truncate text-sm font-extrabold text-ink">
              {item.title}
            </span>
            <Pill
              variant="status"
              tone={STATUS_TONE[item.status]}
              label={item.status}
            />
          </div>
          {item.notes ? (
            <p className="text-sm text-muted">{item.notes}</p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-xs">
          <button
            type="button"
            className={iconButtonClass()}
            disabled={!canMoveUp || busy}
            aria-label="Move up"
            onClick={onMoveUp}
          >
            ↑
          </button>
          <button
            type="button"
            className={iconButtonClass()}
            disabled={!canMoveDown || busy}
            aria-label="Move down"
            onClick={onMoveDown}
          >
            ↓
          </button>
          <button
            type="button"
            className={iconButtonClass()}
            disabled={busy}
            aria-label="Edit item"
            onClick={onEdit}
          >
            ✎
          </button>
          <button
            type="button"
            className={iconButtonClass()}
            disabled={busy}
            aria-label="Delete item"
            onClick={onDelete}
          >
            ✕
          </button>
        </div>
      </div>
    </li>
  );
}
