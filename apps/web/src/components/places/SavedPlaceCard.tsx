"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
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

/** Up to two initials from the place name, for the avatar tile. */
function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "•";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

// Soft, friendly avatar tints — seeded by name so each place stays recognisable.
const AVATAR_TINTS = [
  "bg-coral-soft text-coral-ink",
  "bg-lime-soft text-on-accent",
  "bg-[#dbeafe] text-[#1e40af]",
  "bg-[#e7e0fb] text-[#5b21b6]",
  "bg-[#d2f2ec] text-[#0f766e]",
] as const;

function tintFor(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return AVATAR_TINTS[h % AVATAR_TINTS.length];
}

function PinIcon() {
  return (
    <svg
      width={13}
      height={13}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0 text-coral"
    >
      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  );
}

export function SavedPlaceCard({
  place,
  onSetFavorite,
  onSetVisited,
  onDelete,
  busy = false,
}: SavedPlaceCardProps) {
  const t = useTranslations("Places");
  const meta = [
    place.city,
    place.category && t.has(`categories.${place.category}`)
      ? t(`categories.${place.category}`)
      : place.category,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Card className="flex flex-col gap-sm">
      <div className="flex items-start gap-sm">
        <span
          aria-hidden="true"
          className={cn(
            "grid size-9 shrink-0 place-items-center rounded-md text-sm font-extrabold",
            tintFor(place.name),
          )}
        >
          {initials(place.name)}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[1.05rem] font-extrabold text-ink">
            {place.name}
          </h3>
          {meta ? (
            <p className="flex items-center gap-xs text-sm text-muted">
              {place.city ? <PinIcon /> : null}
              <span className="truncate">{meta}</span>
            </p>
          ) : null}
        </div>
        <span className="shrink-0 text-xs font-bold tabular-nums text-muted">
          {place.short_code}
        </span>
      </div>

      {place.notes ? (
        <p className="line-clamp-3 text-sm text-muted">{place.notes}</p>
      ) : null}

      <div className="mt-auto flex items-center gap-xs pt-sm">
        <Button
          variant={place.favorite ? "primary" : "ghost"}
          aria-pressed={place.favorite}
          disabled={busy}
          onClick={() => onSetFavorite(!place.favorite)}
        >
          {place.favorite ? t("card.favoriteOn") : t("card.favoriteOff")}
        </Button>
        <Button
          variant={place.visited ? "primary" : "ghost"}
          aria-pressed={place.visited}
          disabled={busy}
          onClick={() => onSetVisited(!place.visited)}
        >
          {place.visited ? t("card.visitedOn") : t("card.visitedOff")}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          disabled={busy}
          aria-label={t("card.removeAria", { name: place.name })}
          title={t("card.removeTitle")}
          className="ml-auto text-muted hover:text-status-cancelled"
          onClick={onDelete}
        >
          <TrashIcon />
        </Button>
      </div>
    </Card>
  );
}
