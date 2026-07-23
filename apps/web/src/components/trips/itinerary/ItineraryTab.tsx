"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";
import { useTrip } from "@/lib/query/trips";
import {
  OverBudgetError,
  useAddItem,
  useDeleteItem,
  useReorderItem,
  useUpdateItem,
  type TripItem,
} from "@/lib/query/items";

import { ItemForm, type ItemFormValues } from "./ItemForm";
import { ItemRow } from "./ItemRow";

type Editing = { mode: "add" } | { mode: "edit"; item: TripItem };

// Day N maps onto a real calendar date (start_date + N-1), pinned to UTC so the
// day never shifts in negative-offset timezones — same convention as the header.
function dayDate(
  format: ReturnType<typeof useFormatter>,
  start: string | null | undefined,
  day: number,
): string | null {
  if (!start) return null;
  const d = new Date(`${start}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + (day - 1));
  return format.dateTime(d, {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

// Which day number (start_date + N-1) is today, or null if today is outside the
// trip window. UTC-pinned to match dayDate so the "Today" marker never drifts.
function todayDayNumber(start: string | null | undefined): number | null {
  if (!start) return null;
  const startMs = Date.parse(`${start}T00:00:00Z`);
  const now = new Date();
  const todayMs = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const diff = Math.round((todayMs - startMs) / 86_400_000);
  return diff >= 0 ? diff + 1 : null;
}

function byDay(items: TripItem[]): [number, TripItem[]][] {
  const groups = new Map<number, TripItem[]>();
  for (const item of items) {
    const bucket = groups.get(item.day) ?? [];
    bucket.push(item);
    groups.set(item.day, bucket);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([day, bucket]) => [
      day,
      [...bucket].sort((a, b) => a.sort_order - b.sort_order),
    ]);
}

export function ItineraryTab({ tripId }: { tripId: string }) {
  const t = useTranslations("Itinerary");
  const format = useFormatter();
  const { data: trip, isLoading } = useTrip(tripId);
  const addItem = useAddItem(tripId);
  const updateItem = useUpdateItem(tripId);
  const deleteItem = useDeleteItem(tripId);
  const reorderItem = useReorderItem(tripId);

  const [editing, setEditing] = useState<Editing | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const items = trip?.items ?? [];
  const groups = byDay(items);
  const todayNum = todayDayNumber(trip?.start_date);
  const mutating = addItem.isPending || updateItem.isPending;

  function closeForm() {
    setEditing(null);
    setNotice(null);
  }

  async function handleSubmit(values: ItemFormValues) {
    setNotice(null);
    try {
      if (editing?.mode === "edit") {
        await updateItem.mutateAsync({
          item: editing.item,
          changes: {
            day: values.day,
            kind: values.kind,
            status: values.status,
            title: values.title,
            place_id: values.place_id,
            start_time: values.start_time,
            notes: values.notes,
          },
        });
      } else {
        // Append after the last item of the target day.
        const dayItems = items.filter((it) => it.day === values.day);
        const sortOrder = dayItems.reduce(
          (max, it) => Math.max(max, it.sort_order + 1),
          0,
        );
        await addItem.mutateAsync({
          day: values.day,
          kind: values.kind,
          status: values.status,
          title: values.title,
          sort_order: sortOrder,
          place_id: values.place_id,
          start_time: values.start_time,
          notes: values.notes,
        });
      }
      closeForm();
    } catch (err) {
      if (err instanceof OverBudgetError) {
        setNotice(
          err.hint
            ? t("overBudgetWithHint", { message: err.message, hint: err.hint })
            : t("overBudget", { message: err.message }),
        );
        return;
      }
      setNotice(t("saveError"));
    }
  }

  if (isLoading) {
    return (
      <section className="flex items-center gap-sm text-sm text-muted">
        <Spinner label={t("loadingLabel")} />
        <span>{t("loading")}</span>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-md">
      <header className="flex items-center justify-between">
        <h2 className="text-lg font-extrabold text-ink">{t("title")}</h2>
        <Button onClick={() => setEditing({ mode: "add" })}>{t("addItem")}</Button>
      </header>

      {groups.length === 0 ? (
        <EmptyState
          icon="🗺️"
          title={t("emptyTitle")}
          hint={t("emptyHint")}
          action={
            <Button onClick={() => setEditing({ mode: "add" })}>
              {t("addItem")}
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-lg">
          {groups.map(([day, dayItems]) => {
            const date = dayDate(format, trip?.start_date, day);
            const isToday = day === todayNum;
            return (
            <div key={day} className="flex flex-col gap-sm">
              <div className="flex items-baseline gap-sm">
                <h3 className="text-sm font-extrabold text-ink">{t("dayHeading", { day })}</h3>
                {date ? (
                  <span className="text-sm text-muted">· {date}</span>
                ) : null}
                {isToday ? (
                  <span className="inline-flex items-center gap-xs rounded-pill bg-lime px-sm py-px text-xs font-bold text-on-accent">
                    <span
                      aria-hidden="true"
                      className="size-1.5 animate-pulse rounded-pill bg-on-accent"
                    />
                    {t("today")}
                  </span>
                ) : null}
                <span className="ml-auto text-xs font-bold text-muted tabular-nums">
                  {t("itemCount", { count: dayItems.length })}
                </span>
              </div>
              {/* The vertical rail threads the day's timeline nodes; the nodes
                  (z-10) sit over it so it reads as a connected route. Today's
                  rail carries the active lime signal. */}
              <ul className="relative flex flex-col gap-sm">
                <span
                  aria-hidden="true"
                  className={cn(
                    "absolute bottom-6 left-4 top-5 w-px",
                    isToday ? "bg-lime" : "bg-line",
                  )}
                />
                {dayItems.map((item, index) => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    canMoveUp={index > 0}
                    canMoveDown={index < dayItems.length - 1}
                    busy={reorderItem.isPending}
                    highlight={isToday}
                    onMoveUp={() =>
                      reorderItem.mutate({
                        a: item,
                        b: dayItems[index - 1],
                      })
                    }
                    onMoveDown={() =>
                      reorderItem.mutate({
                        a: item,
                        b: dayItems[index + 1],
                      })
                    }
                    onEdit={() => setEditing({ mode: "edit", item })}
                    onDelete={() => deleteItem.mutate(item.id)}
                  />
                ))}
              </ul>
            </div>
            );
          })}
        </div>
      )}

      {editing ? (
        <ItemForm
          open
          title={editing.mode === "edit" ? t("form.editTitle") : t("form.addTitle")}
          initial={editing.mode === "edit" ? editing.item : undefined}
          submitting={mutating}
          notice={notice}
          onSubmit={handleSubmit}
          onClose={closeForm}
        />
      ) : null}
    </section>
  );
}
