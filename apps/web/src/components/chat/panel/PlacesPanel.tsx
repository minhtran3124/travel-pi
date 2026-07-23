"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { cn } from "@/lib/cn";
import type { PlacesPanelData, PlacesPanelPlace } from "@/lib/stream/panel";

/**
 * Places side-panel (specs/places-side-panel) — a compact list so every result is
 * visible without scrolling the chat. One row per place: a thumbnail, name,
 * category, guest rating, and price band; click a row to expand detail
 * (description, reviews, tags, opening hours). Curated `is_recommended` picks are
 * ringed in lime — places have no natural "cheapest"-style best metric. Read-only.
 * Pure render + local expand state.
 */

function priceBand(level: number): string {
  return level > 0 ? "$".repeat(level) : "—";
}

function Row({ p }: { p: PlacesPanelPlace }) {
  const t = useTranslations("Panel");
  const [open, setOpen] = useState(false);
  const [imgError, setImgError] = useState(false);
  return (
    <div
      className={cn(
        "rounded-[11px] border border-line bg-panel shadow-card transition duration-150 hover:-translate-y-0.5 hover:border-faint hover:shadow-lift",
        p.is_recommended && "ring-2 ring-lime",
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
              📍
            </span>
          ) : (
            /* eslint-disable-next-line @next/next/no-img-element -- side-panel thumbnail: external image_url across many
               unconfigured domains; next/image would need remotePatterns for each. */
            <img
              src={p.image_url}
              alt={p.name}
              loading="lazy"
              referrerPolicy="no-referrer"
              onError={() => setImgError(true)}
              className="h-full w-full object-cover"
            />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-bold text-ink">{p.name}</div>
          <div className="truncate text-[11.5px] text-muted">
            <span className="capitalize">{p.category}</span>
            {" · "}
            <span className="text-amber-500">★</span>{" "}
            <span className="tabular-nums">{p.rating.toFixed(1)}</span>
            {" · "}
            <span className="tabular-nums">{priceBand(p.price_level)}</span>
          </div>
          <div className="truncate text-[11px] text-faint">{p.address}</div>
        </div>
        {p.is_recommended && (
          <div className="shrink-0 text-[10.5px] font-bold text-lime">★ {t("places.pick")}</div>
        )}
      </button>
      {open && (
        <div className="border-t border-line px-3 py-2.5">
          <p className="mb-2 text-[12px] text-ink">{p.description}</p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
            <Detail k={t("places.category")} v={p.category} className="capitalize" />
            <Detail
              k={t("places.rating")}
              v={t("places.ratingValue", { rating: p.rating.toFixed(1), count: p.review_count })}
            />
            <Detail k={t("places.price")} v={priceBand(p.price_level)} />
            <Detail k={t("places.hours")} v={p.opening_hours ?? "—"} />
            <div className="col-span-2">
              <dt className="text-muted">{t("places.address")}</dt>
              <dd className="font-semibold text-ink">{p.address}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-muted">{t("places.tags")}</dt>
              <dd className="font-semibold text-ink">
                {p.tags.length ? p.tags.join(", ") : "—"}
              </dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  );
}

function Detail({ k, v, className }: { k: string; v: string; className?: string }) {
  return (
    <div>
      <dt className="text-muted">{k}</dt>
      <dd className={cn("font-semibold text-ink", className)}>{v}</dd>
    </div>
  );
}

export function PlacesPanel({ data }: { data: PlacesPanelData }) {
  const t = useTranslations("Panel");
  const { city, category, results_count, places } = data;
  const summary = [city, category].filter(Boolean).join(" · ");
  return (
    <div className="h-full overflow-y-auto p-md">
      <div className="mb-2.5">
        <div className="text-[15px] font-bold text-ink">
          {summary || t("places.fallbackTitle")}
        </div>
        <div className="text-[12.5px] text-muted">
          {t("places.results", { count: results_count })}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {places.map((p, i) => (
          <div
            key={p.id}
            className="tp-row-in"
            style={{ animationDelay: `${Math.min(i, 10) * 50}ms` }}
          >
            <Row p={p} />
          </div>
        ))}
      </div>
    </div>
  );
}
