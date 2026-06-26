"use client";

import { Pill } from "@/components/ui/Pill";
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
  onMoveUp: () => void;
  onMoveDown: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

function iconButtonClass(): string {
  return "inline-flex size-7 items-center justify-center rounded-sm border border-line bg-transparent text-sm text-muted transition hover:border-ink hover:text-muted disabled:cursor-not-allowed disabled:opacity-40";
}

export function ItemRow({
  item,
  canMoveUp,
  canMoveDown,
  busy = false,
  onMoveUp,
  onMoveDown,
  onEdit,
  onDelete,
}: ItemRowProps) {
  return (
    <li className="flex items-start gap-md rounded-md border border-line-soft bg-panel-raised p-md">
      <span className="text-lg leading-none" aria-hidden="true">
        {KIND_ICON[item.kind]}
      </span>

      <div className="flex min-w-0 flex-1 flex-col gap-xs">
        <div className="flex flex-wrap items-center gap-sm">
          <span className="truncate text-sm font-extrabold text-ink">
            {item.title}
          </span>
          <Pill
            variant="status"
            tone={STATUS_TONE[item.status]}
            label={item.status}
          />
          {item.start_time ? (
            <span className="font-mono text-xs tabular-nums text-muted">
              {item.start_time}
            </span>
          ) : null}
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
    </li>
  );
}
