"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { useCreateTrip, type TripCreate } from "@/lib/query/trips";

interface NewTripModalProps {
  open: boolean;
  onClose: () => void;
  onCreated?: (id: string) => void;
}

const EMPTY = {
  title: "",
  city: "",
  start_date: "",
  end_date: "",
  travelers: "1",
  notes: "",
};

export function NewTripModal({ open, onClose, onCreated }: NewTripModalProps) {
  const [form, setForm] = useState(EMPTY);
  const createTrip = useCreateTrip();

  function set<K extends keyof typeof EMPTY>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function close() {
    setForm(EMPTY);
    createTrip.reset();
    onClose();
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const travelers = Number.parseInt(form.travelers, 10);
    const body: TripCreate = {
      title: form.title.trim(),
      travelers: Number.isNaN(travelers) ? 1 : travelers,
      city: form.city.trim() || null,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      notes: form.notes.trim() || null,
    };
    createTrip.mutate(body, {
      onSuccess: (trip) => {
        onCreated?.(trip.id);
        close();
      },
    });
  }

  return (
    <Modal open={open} onClose={close} title="New trip">
      <form onSubmit={onSubmit} className="flex flex-col gap-md">
        <Field
          label="Title"
          required
          value={form.title}
          onChange={(e) => set("title", e.target.value)}
          placeholder="Da Nang long weekend"
        />
        <Field
          label="City"
          value={form.city}
          onChange={(e) => set("city", e.target.value)}
          placeholder="Da Nang"
        />
        <div className="flex gap-md">
          <Field
            label="Start date"
            type="date"
            className="w-full"
            value={form.start_date}
            onChange={(e) => set("start_date", e.target.value)}
          />
          <Field
            label="End date"
            type="date"
            className="w-full"
            value={form.end_date}
            onChange={(e) => set("end_date", e.target.value)}
          />
        </div>
        <Field
          label="Travelers"
          type="number"
          min={1}
          max={50}
          value={form.travelers}
          onChange={(e) => set("travelers", e.target.value)}
        />
        <div className="flex flex-col gap-xs">
          <label
            htmlFor="new-trip-notes"
            className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted"
          >
            Notes
          </label>
          <textarea
            id="new-trip-notes"
            rows={3}
            value={form.notes}
            onChange={(e) => set("notes", e.target.value)}
            className="rounded-sm border border-line bg-panel-raised px-sm py-xs text-sm text-ink placeholder:text-muted"
          />
        </div>

        {createTrip.isError ? (
          <p className="text-sm font-bold text-status-cancelled">
            Could not create the trip. Please try again.
          </p>
        ) : null}

        <div className="mt-sm flex justify-end gap-sm">
          <Button type="button" variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={createTrip.isPending || form.title.trim() === ""}
          >
            {createTrip.isPending ? <Spinner label="Creating trip" /> : "Create trip"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
