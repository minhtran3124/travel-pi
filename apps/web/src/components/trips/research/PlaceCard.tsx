"use client";

import { useState } from "react";

import { usePlaceLookup } from "@/lib/query/research";
import type { ProposalItinerary } from "./proposal";

/**
 * One itinerary stop. Resolves the place through `GET /places/{id}`; while it
 * loads a skeleton shows, and if the lookup fails the card degrades to the
 * stop's own prose (title/notes from the proposal) rather than blanking. The
 * checkbox opts the stop in/out of Apply — checked by default.
 */
export function PlaceCard({
  entry,
  checked,
  onToggle,
  toggleLabel,
}: {
  entry: ProposalItinerary;
  checked: boolean;
  onToggle: (next: boolean) => void;
  toggleLabel: string;
}) {
  const place = usePlaceLookup(entry.place_id);
  const [imgError, setImgError] = useState(false);

  return (
    <div className="flex items-center gap-sm rounded-sm border border-line-soft bg-panel px-sm py-xs">
      {entry.time ? (
        <span className="w-12 shrink-0 text-xs font-bold tabular-nums text-muted">
          {entry.time}
        </span>
      ) : null}

      <div className="relative size-10 shrink-0 overflow-hidden rounded-[8px] bg-panel-raised">
        {place.data && !imgError ? (
          /* eslint-disable-next-line @next/next/no-img-element -- external image_url across
             unconfigured domains; next/image would need remotePatterns for each. */
          <img
            src={place.data.image_url}
            alt={place.data.name}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setImgError(true)}
            className="h-full w-full object-cover"
          />
        ) : (
          <span className="grid h-full w-full place-items-center text-sm" aria-hidden="true">
            📍
          </span>
        )}
      </div>

      <div className="min-w-0 flex-1">
        {place.isPending ? (
          <div className="h-4 w-32 animate-pulse rounded-sm bg-panel-raised" />
        ) : (
          <div className="overflow-hidden text-ellipsis whitespace-nowrap text-sm font-bold text-ink">
            {place.data?.name ?? entry.title}
          </div>
        )}
        <div className="overflow-hidden text-ellipsis whitespace-nowrap text-xs text-muted">
          {place.data ? (
            <>
              <span className="capitalize">{place.data.category}</span>
              {" · "}
              <span className="text-amber-500">★</span>{" "}
              <span className="tabular-nums">{place.data.rating.toFixed(1)}</span>
            </>
          ) : (
            entry.notes ?? null
          )}
        </div>
      </div>

      <label className="flex shrink-0 cursor-pointer items-center">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onToggle(e.target.checked)}
          aria-label={toggleLabel}
          className="size-4 accent-lime"
        />
      </label>
    </div>
  );
}
