"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { BrowseDrawer } from "@/components/places/BrowseDrawer";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import type { Place, PlaceSource } from "@/lib/query/places";
import { useSavedPlaces } from "@/lib/query/places";
import {
  AlreadyShortlistedError,
  useAddToShortlist,
  useRemoveFromShortlist,
  useShortlist,
  type ShortlistEntry,
} from "@/lib/query/shortlist";

function entryMeta(entry: ShortlistEntry): string {
  const place = entry.place;
  return [place.city, place.category].filter(Boolean).join(" · ");
}

export function ShortlistTab({ tripId }: { tripId: string }) {
  const t = useTranslations("Shortlist");
  const [browseOpen, setBrowseOpen] = useState(false);
  const [savedOpen, setSavedOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const { data: entries, isLoading, isError } = useShortlist(tripId);
  const add = useAddToShortlist(tripId);
  const remove = useRemoveFromShortlist(tripId);
  const saved = useSavedPlaces();

  const busy = add.isPending || remove.isPending;

  function handleAdd(placeId: string, source: PlaceSource, name: string) {
    setNotice(null);
    add.mutate(
      { place_id: placeId, source },
      {
        onError: (err) => {
          if (err instanceof AlreadyShortlistedError) {
            setNotice(t("alreadyShortlisted", { name }));
          } else {
            setNotice(t("addError", { name }));
          }
        },
      },
    );
  }

  function handlePickCatalog(place: Place) {
    handleAdd(place.id, "catalog", place.name);
    setBrowseOpen(false);
  }

  return (
    <section className="flex flex-col gap-md">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <h2 className="text-lg font-extrabold text-ink">{t("title")}</h2>
        <div className="flex gap-xs">
          <Button onClick={() => setBrowseOpen(true)}>{t("addFromCatalog")}</Button>
          <Button
            variant="ghost"
            onClick={() => setSavedOpen((v) => !v)}
            aria-pressed={savedOpen}
          >
            {t("addFromSaved")}
          </Button>
        </div>
      </div>

      {notice ? (
        <p
          role="status"
          className="rounded-sm border border-line bg-panel-raised px-sm py-xs text-sm text-muted"
        >
          {notice}
        </p>
      ) : null}

      {savedOpen ? (
        <Card className="flex flex-col gap-sm">
          <h3 className="text-sm font-bold uppercase tracking-[0.08em] text-muted">
            {t("savedPlaces")}
          </h3>
          {saved.isLoading ? (
            <Spinner label={t("loadingSavedLabel")} />
          ) : !saved.data || saved.data.results.length === 0 ? (
            <p className="text-sm text-muted">{t("noSavedYet")}</p>
          ) : (
            <ul className="flex flex-col gap-xs">
              {saved.data.results.map((p) => (
                <li
                  key={p.id}
                  className="flex items-center justify-between gap-sm rounded-sm border border-line-soft p-sm"
                >
                  <span className="truncate text-sm text-ink">{p.name}</span>
                  <Button
                    className="shrink-0"
                    disabled={busy}
                    onClick={() => handleAdd(p.id, "saved", p.name)}
                  >
                    {t("add")}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {isLoading ? (
        <div className="flex justify-center py-xl">
          <Spinner label={t("loadingLabel")} />
        </div>
      ) : isError ? (
        <EmptyState
          icon="⚠️"
          title={t("errorTitle")}
          hint={t("errorHint")}
        />
      ) : !entries || entries.length === 0 ? (
        <EmptyState
          icon="📍"
          title={t("emptyTitle")}
          hint={t("emptyHint")}
        />
      ) : (
        <ul className="flex flex-col gap-sm">
          {entries.map((entry) => {
            const meta = entryMeta(entry);
            return (
              <li key={entry.link_id}>
                <Card className="flex items-start justify-between gap-sm">
                  <div className="min-w-0">
                    <div className="flex items-center gap-xs">
                      <h3 className="truncate font-extrabold text-ink">
                        {entry.place.name}
                      </h3>
                      <span className="inline-flex shrink-0 items-center rounded-pill bg-panel-raised px-sm py-px text-xs font-bold capitalize text-muted ring-1 ring-line">
                        {entry.source}
                      </span>
                    </div>
                    {meta ? (
                      <p className="truncate text-sm text-muted">{meta}</p>
                    ) : null}
                  </div>
                  <Button
                    variant="ghost"
                    className="shrink-0"
                    disabled={busy}
                    aria-label={t("removeAria", { name: entry.place.name })}
                    onClick={() => remove.mutate(entry.link_id)}
                  >
                    {t("remove")}
                  </Button>
                </Card>
              </li>
            );
          })}
        </ul>
      )}

      <BrowseDrawer
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        onPick={handlePickCatalog}
        mode="shortlist"
      />
    </section>
  );
}
