"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
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
  const { data: trip, isLoading } = useTrip(tripId);
  const addItem = useAddItem(tripId);
  const updateItem = useUpdateItem(tripId);
  const deleteItem = useDeleteItem(tripId);
  const reorderItem = useReorderItem(tripId);

  const [editing, setEditing] = useState<Editing | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const items = trip?.items ?? [];
  const groups = byDay(items);
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
            ? `Over budget — ${err.message} (${err.hint})`
            : `Over budget — ${err.message}`,
        );
        return;
      }
      setNotice("Could not save the item. Please try again.");
    }
  }

  if (isLoading) {
    return (
      <section className="flex items-center gap-sm text-sm text-muted">
        <Spinner label="Loading itinerary" />
        <span>Loading itinerary…</span>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-md">
      <header className="flex items-center justify-between">
        <h2 className="text-lg font-extrabold text-ink">Itinerary</h2>
        <Button onClick={() => setEditing({ mode: "add" })}>Add item</Button>
      </header>

      {groups.length === 0 ? (
        <EmptyState
          icon="🗺️"
          title="No itinerary items yet"
          hint="Plan your days — add a place, meal, or transport leg."
          action={
            <Button onClick={() => setEditing({ mode: "add" })}>
              Add item
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-lg">
          {groups.map(([day, dayItems]) => (
            <div key={day} className="flex flex-col gap-sm">
              <h3 className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
                Day {day}
              </h3>
              <ul className="flex flex-col gap-sm">
                {dayItems.map((item, index) => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    canMoveUp={index > 0}
                    canMoveDown={index < dayItems.length - 1}
                    busy={reorderItem.isPending}
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
          ))}
        </div>
      )}

      {editing ? (
        <ItemForm
          open
          title={editing.mode === "edit" ? "Edit item" : "Add item"}
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
