"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import {
  usePlaceSearch,
  type Place,
  type PlaceCategory,
  type PlaceSearchFilters,
  type PlaceSource,
} from "@/lib/query/places";

/**
 * Stable, self-contained contract — Task 2.6 (shortlist) imports this component
 * as-is and only swaps `mode`/`onPick`. Do NOT add page-specific props here.
 */
export interface BrowseDrawerProps {
  open: boolean;
  onClose: () => void;
  /** Called when the user picks a catalog result. `source` is always "catalog" here. */
  onPick: (place: Place, source: PlaceSource) => void;
  /** Drives the per-result action label. "save" (default) vs "shortlist". */
  mode?: "save" | "shortlist";
}

const CATEGORIES: PlaceCategory[] = [
  "attraction",
  "restaurant",
  "cafe",
  "activity",
  "nightlife",
  "shopping",
];

export function BrowseDrawer({
  open,
  onClose,
  onPick,
  mode = "save",
}: BrowseDrawerProps) {
  const t = useTranslations("Places");
  const [city, setCity] = useState("");
  const [category, setCategory] = useState<PlaceCategory | "">("");

  const filters: PlaceSearchFilters = {
    ...(city.trim() ? { city: city.trim() } : {}),
    ...(category ? { category } : {}),
  };
  const hasQuery = Boolean(filters.city || filters.category);

  const { data, isFetching, isError } = usePlaceSearch(filters, open && hasQuery);
  const results = data?.results ?? [];
  const actionLabel =
    mode === "shortlist" ? t("browse.add") : t("browse.save");

  return (
    <Modal open={open} onClose={onClose} title={t("browse.title")}>
      <div className="flex flex-col gap-md">
        <div className="flex flex-wrap items-end gap-sm">
          <Field
            label={t("browse.cityLabel")}
            placeholder={t("browse.cityPlaceholder")}
            value={city}
            onChange={(e) => setCity(e.target.value)}
            wrapperClassName="min-w-[10rem] flex-1"
          />
          <Select
            label={t("browse.categoryLabel")}
            id="browse-category"
            value={category}
            onChange={(e) => setCategory(e.target.value as PlaceCategory | "")}
            wrapperClassName="min-w-[9rem] flex-1"
          >
            <option value="">{t("browse.categoryAny")}</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c} className="capitalize">
                {t(`categories.${c}`)}
              </option>
            ))}
          </Select>
        </div>

        <div className="max-h-[50vh] overflow-y-auto">
          {!hasQuery ? (
            <EmptyState
              icon="🔎"
              title={t("browse.searchTitle")}
              hint={t("browse.searchHint")}
            />
          ) : isFetching ? (
            <div className="flex justify-center py-xl">
              <Spinner label={t("browse.searchingLabel")} />
            </div>
          ) : isError ? (
            <EmptyState
              icon="⚠️"
              title={t("browse.searchFailedTitle")}
              hint={t("browse.searchFailedHint")}
            />
          ) : results.length === 0 ? (
            <EmptyState
              icon="🗺️"
              title={t("browse.noResultsTitle")}
              hint={t("browse.noResultsHint")}
            />
          ) : (
            <ul className="flex flex-col gap-xs">
              {results.map((place) => (
                <li
                  key={place.id}
                  className="flex items-center justify-between gap-sm rounded-sm border border-line-soft p-sm"
                >
                  <div className="min-w-0">
                    <p className="truncate font-bold text-ink">{place.name}</p>
                    <p className="truncate text-xs text-muted">
                      {[
                        place.city,
                        place.category && t.has(`categories.${place.category}`)
                          ? t(`categories.${place.category}`)
                          : place.category,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                      {" · "}
                      <span className="tabular-nums">
                        ★ {place.rating.toFixed(1)}
                      </span>
                    </p>
                  </div>
                  <Button
                    className="shrink-0"
                    onClick={() => onPick(place, "catalog")}
                  >
                    {actionLabel}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  );
}
