"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Meter } from "@/components/ui/Meter";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";
import {
  useBudget,
  useSetBudget,
  type CategoryBudget,
  type TripBudgetSet,
} from "@/lib/query/budget";

const CATEGORIES = ["flights", "hotels", "activities", "buffer"] as const;
type CategoryKey = (typeof CATEGORIES)[number];

const LABELS: Record<CategoryKey, string> = {
  flights: "Flights",
  hotels: "Hotels",
  activities: "Activities",
  buffer: "Buffer",
};

function usd(value: number): string {
  return value.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function CategoryRow({
  label,
  cat,
}: {
  label: string;
  cat: CategoryBudget;
}) {
  const over = cat.remaining !== null && cat.remaining !== undefined && cat.remaining < 0;
  const capped = cat.cap !== null && cat.cap !== undefined;
  return (
    <div className="flex flex-col gap-xs border-b border-line py-sm last:border-b-0">
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold text-ink">{label}</span>
        <div className="flex items-center gap-lg text-sm tabular-nums">
          <span className="w-16 text-right text-muted">
            {capped ? usd(cat.cap as number) : "—"}
          </span>
          <span className="w-16 text-right text-ink">{usd(cat.spent)}</span>
          <span
            className={cn(
              "w-16 text-right",
              over ? "font-bold text-status-cancelled" : "text-muted",
            )}
          >
            {cat.remaining === null || cat.remaining === undefined
              ? "—"
              : usd(cat.remaining)}
          </span>
        </div>
      </div>
      {capped ? <Meter value={cat.spent} max={cat.cap} /> : null}
    </div>
  );
}

function EditCapsForm({
  tripId,
  initial,
  onDone,
}: {
  tripId: string;
  initial: TripBudgetSet;
  onDone: () => void;
}) {
  const setBudget = useSetBudget(tripId);
  const [values, setValues] = useState<Record<CategoryKey, string>>({
    flights: initial.flights != null ? String(initial.flights) : "",
    hotels: initial.hotels != null ? String(initial.hotels) : "",
    activities: initial.activities != null ? String(initial.activities) : "",
    buffer: initial.buffer != null ? String(initial.buffer) : "",
  });

  function submit() {
    const body: TripBudgetSet = {};
    for (const key of CATEGORIES) {
      const raw = values[key].trim();
      body[key] = raw === "" ? null : Number(raw);
    }
    setBudget.mutate(body, { onSuccess: onDone });
  }

  return (
    <div className="flex flex-col gap-md">
      <p className="text-sm text-muted">
        Set a cap per category, in USD. Leave a field blank to leave it uncapped.
        Saving replaces all caps.
      </p>
      {CATEGORIES.map((key) => (
        <Field
          key={key}
          label={`${LABELS[key]} cap (USD)`}
          type="number"
          min={0}
          step="0.01"
          inputMode="decimal"
          value={values[key]}
          onChange={(e) =>
            setValues((v) => ({ ...v, [key]: e.target.value }))
          }
        />
      ))}
      {setBudget.isError ? (
        <p className="text-sm text-status-cancelled">
          Couldn&apos;t save the budget. Try again.
        </p>
      ) : null}
      <div className="flex justify-end gap-sm">
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={setBudget.isPending}>
          {setBudget.isPending ? "Saving…" : "Save caps"}
        </Button>
      </div>
    </div>
  );
}

export function BudgetTab({ tripId }: { tripId: string }) {
  const { data, isPending, isError } = useBudget(tripId);
  const [editing, setEditing] = useState(false);

  if (isPending) {
    return (
      <section className="flex items-center gap-sm text-sm text-muted">
        <Spinner label="Loading budget" />
        <span>Loading budget…</span>
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section>
        <EmptyState
          icon="💸"
          title="Couldn't load the budget"
          hint="Something went wrong fetching this trip's budget."
        />
      </section>
    );
  }

  const initial: TripBudgetSet = {
    flights: data.categories.flights.cap ?? null,
    hotels: data.categories.hotels.cap ?? null,
    activities: data.categories.activities.cap ?? null,
    buffer: data.categories.buffer.cap ?? null,
  };

  return (
    <section className="flex flex-col gap-md">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-extrabold text-ink">Budget</h2>
        <Button variant="ghost" onClick={() => setEditing(true)}>
          Edit caps
        </Button>
      </div>

      {data.over_budget ? (
        <div
          role="alert"
          className="rounded-sm border border-status-cancelled bg-status-cancelled/10 px-md py-sm text-sm font-bold text-status-cancelled"
        >
          Over budget — spend exceeds a category cap.
        </div>
      ) : null}

      <Card className="flex flex-col">
        <div className="flex items-center justify-between pb-xs text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
          <span>Category</span>
          <div className="flex items-center gap-lg">
            <span className="w-16 text-right">Cap</span>
            <span className="w-16 text-right">Spent</span>
            <span className="w-16 text-right">Left</span>
          </div>
        </div>
        {CATEGORIES.map((key) => (
          <CategoryRow
            key={key}
            label={LABELS[key]}
            cat={data.categories[key]}
          />
        ))}
        <div className="flex flex-col gap-xs pt-sm">
          <div className="flex items-center justify-between text-sm font-extrabold text-ink">
            <span>Total</span>
            <div className="flex items-center gap-lg tabular-nums">
              <span className="w-16 text-right text-muted">
                {data.total_cap == null ? "—" : usd(data.total_cap)}
              </span>
              <span className="w-16 text-right">{usd(data.total_spent)}</span>
              <span
                className={cn(
                  "w-16 text-right",
                  data.total_remaining != null && data.total_remaining < 0
                    ? "text-status-cancelled"
                    : "",
                )}
              >
                {data.total_remaining == null ? "—" : usd(data.total_remaining)}
              </span>
            </div>
          </div>
          {data.total_cap != null ? (
            <Meter value={data.total_spent} max={data.total_cap} />
          ) : null}
        </div>
      </Card>

      <Modal
        open={editing}
        onClose={() => setEditing(false)}
        title="Edit budget caps"
      >
        <EditCapsForm
          tripId={tripId}
          initial={initial}
          onDone={() => setEditing(false)}
        />
      </Modal>
    </section>
  );
}
