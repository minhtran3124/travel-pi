"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { cn } from "@/lib/cn";
import type { HotelsPanelHotel } from "@/lib/stream/panel";

function stars(n: number): string {
  return "★".repeat(n) + "☆".repeat(Math.max(0, 5 - n));
}

export function HotelResultCard({ h, cheapest }: { h: HotelsPanelHotel; cheapest: boolean }) {
  const t = useTranslations("Panel");
  const [open, setOpen] = useState(false);
  const [imgError, setImgError] = useState(false);
  return (
    <div
      className={cn(
        "rounded-[11px] border border-line bg-panel shadow-card transition duration-150 hover:-translate-y-0.5 hover:border-faint hover:shadow-lift",
        cheapest && "ring-2 ring-lime",
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center gap-2.5 px-3 py-2.5 text-left active:translate-y-px"
      >
        <div className="relative size-12 shrink-0 overflow-hidden rounded-[8px] bg-panel-raised">
          {imgError ? (
            <span className="grid h-full w-full place-items-center text-lg" aria-hidden="true">
              🏨
            </span>
          ) : (
            /* eslint-disable-next-line @next/next/no-img-element -- side-panel thumbnail: external image_url across many
               unconfigured domains; next/image would need remotePatterns for each. */
            <img
              src={h.image_url}
              alt={h.name}
              loading="lazy"
              referrerPolicy="no-referrer"
              onError={() => setImgError(true)}
              className="h-full w-full object-cover"
            />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-bold text-ink">{h.name}</div>
          <div className="truncate text-[11.5px] text-muted">
            <span className="text-amber-500">{stars(h.star_rating)}</span>{" "}
            <span className="tabular-nums">{h.rating.toFixed(1)}</span>
            {" · "}
            <span className="tabular-nums">${Math.round(h.price_per_night)}</span>
            {t("hotels.perNight")}
            {" · "}
            {h.available
              ? t("hotels.roomsLeft", { count: h.available_rooms })
              : t("hotels.full")}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[15px] font-extrabold tabular-nums text-ink">
            ${Math.round(h.total_price)}
          </div>
          <div
            className="text-[10.5px] font-bold"
            style={{
              color: h.available
                ? "var(--color-status-confirmed)"
                : "var(--color-coral-ink)",
            }}
          >
            {h.available ? t("hotels.available") : t("hotels.full")}
          </div>
        </div>
      </button>
      {open && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-line px-3 py-2.5 text-[12px]">
          {h.description && (
            <p className="col-span-2 mb-1 text-[12px] text-ink">{h.description}</p>
          )}
          <Detail k={t("hotels.stars")} v={stars(h.star_rating)} />
          <Detail
            k={t("hotels.guestRating")}
            v={t("hotels.guestRatingValue", { rating: h.rating.toFixed(1), count: h.review_count })}
          />
          <Detail k={t("hotels.nightlyRate")} v={`${h.price_per_night.toFixed(2)} ${h.currency}`} />
          <Detail k={t("hotels.allInTotal")} v={`${h.total_price.toFixed(2)} ${h.currency}`} />
          <Detail k={t("hotels.roomsLeftLabel")} v={String(h.available_rooms)} />
          <div className="col-span-2">
            <dt className="text-muted">{t("hotels.amenities")}</dt>
            <dd className="font-semibold text-ink">
              {h.amenities.length ? h.amenities.join(", ") : "—"}
            </dd>
          </div>
        </dl>
      )}
    </div>
  );
}

function Detail({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-muted">{k}</dt>
      <dd className="font-semibold text-ink">{v}</dd>
    </div>
  );
}
