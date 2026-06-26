"use client";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { SavedPlace } from "@/lib/query/places";

export interface SavedPlaceCardProps {
  place: SavedPlace;
  /** SET the favorite flag to `value` (not a toggle — caller passes the target). */
  onSetFavorite: (value: boolean) => void;
  /** SET the visited flag to `value`. */
  onSetVisited: (value: boolean) => void;
  onDelete: () => void;
  /** Disables the action buttons while a mutation is in flight. */
  busy?: boolean;
}

function metaLine(place: SavedPlace): string {
  return [place.city, place.category].filter(Boolean).join(" · ");
}

export function SavedPlaceCard({
  place,
  onSetFavorite,
  onSetVisited,
  onDelete,
  busy = false,
}: SavedPlaceCardProps) {
  const meta = metaLine(place);
  return (
    <Card className="flex flex-col gap-sm">
      <div className="flex items-start justify-between gap-sm">
        <div className="min-w-0">
          <h3 className="truncate text-[1.05rem] font-extrabold text-ink">
            {place.name}
          </h3>
          {meta ? <p className="text-sm text-muted">{meta}</p> : null}
        </div>
        <span className="shrink-0 text-xs font-bold tabular-nums text-muted">
          {place.short_code}
        </span>
      </div>

      {place.notes ? (
        <p className="line-clamp-3 text-sm text-muted">{place.notes}</p>
      ) : null}

      <div className="mt-auto flex flex-wrap items-center gap-xs pt-sm">
        <Button
          variant={place.favorite ? "primary" : "ghost"}
          aria-pressed={place.favorite}
          disabled={busy}
          onClick={() => onSetFavorite(!place.favorite)}
        >
          {place.favorite ? "★ Favorite" : "☆ Favorite"}
        </Button>
        <Button
          variant={place.visited ? "primary" : "ghost"}
          aria-pressed={place.visited}
          disabled={busy}
          onClick={() => onSetVisited(!place.visited)}
        >
          {place.visited ? "✓ Visited" : "Visited"}
        </Button>
        <Button
          variant="ghost"
          disabled={busy}
          aria-label={`Remove ${place.name}`}
          className="ml-auto"
          onClick={onDelete}
        >
          Remove
        </Button>
      </div>
    </Card>
  );
}
