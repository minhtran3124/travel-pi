"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { Textarea } from "@/components/ui/Textarea";
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
  const t = useTranslations("Trips.newTripModal");
  const [form, setForm] = useState(EMPTY);
  const createTrip = useCreateTrip();

  function set<K extends keyof typeof EMPTY>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  const isDirty = (Object.keys(EMPTY) as (keyof typeof EMPTY)[]).some(
    (k) => form[k] !== EMPTY[k],
  );

  // ISO date strings (YYYY-MM-DD) compare lexicographically, so a plain string
  // comparison correctly orders the two dates.
  const dateError =
    form.start_date && form.end_date && form.end_date < form.start_date
      ? t("dateError")
      : null;

  function close() {
    setForm(EMPTY);
    createTrip.reset();
    onClose();
  }

  // Guard the destructive close paths (backdrop click, Esc, Cancel) so a stray
  // click doesn't silently wipe a half-filled form.
  function requestClose() {
    if (isDirty && !window.confirm(t("discardConfirm"))) {
      return;
    }
    close();
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (dateError) return;
    const parsed = Number.parseInt(form.travelers, 10);
    const travelers = Number.isNaN(parsed) ? 1 : Math.min(50, Math.max(1, parsed));
    const body: TripCreate = {
      title: form.title.trim(),
      travelers,
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
    <Modal open={open} onClose={requestClose} title={t("title")}>
      <p className="-mt-xs mb-md text-sm text-muted">{t("intro")}</p>
      <form onSubmit={onSubmit} className="flex flex-col gap-md">
        <Field
          label={t("tripNameLabel")}
          required
          value={form.title}
          onChange={(e) => set("title", e.target.value)}
          placeholder={t("tripNamePlaceholder")}
          autoComplete="off"
          data-1p-ignore
          data-lpignore="true"
        />
        <Field
          label={t("cityLabel")}
          value={form.city}
          onChange={(e) => set("city", e.target.value)}
          placeholder={t("cityPlaceholder")}
          autoComplete="off"
          data-1p-ignore
          data-lpignore="true"
        />
        <div className="flex flex-col gap-xs">
          <div className="flex gap-md">
            <Field
              label={t("startDateLabel")}
              type="date"
              wrapperClassName="flex-1"
              value={form.start_date}
              aria-invalid={dateError ? true : undefined}
              onChange={(e) => set("start_date", e.target.value)}
            />
            <Field
              label={t("endDateLabel")}
              type="date"
              wrapperClassName="flex-1"
              value={form.end_date}
              aria-invalid={dateError ? true : undefined}
              onChange={(e) => set("end_date", e.target.value)}
            />
          </div>
          {dateError ? (
            <p role="alert" className="text-xs font-bold text-status-cancelled">
              {dateError}
            </p>
          ) : null}
        </div>
        <Field
          label={t("travelersLabel")}
          type="number"
          min={1}
          max={50}
          value={form.travelers}
          onChange={(e) => set("travelers", e.target.value)}
        />
        <Textarea
          label={t("notesLabel")}
          rows={3}
          value={form.notes}
          onChange={(e) => set("notes", e.target.value)}
        />

        {createTrip.isError ? (
          <p role="alert" className="text-sm font-bold text-status-cancelled">
            {t("createError")}
          </p>
        ) : null}

        <div className="mt-sm flex justify-end gap-sm">
          <Button type="button" variant="ghost" onClick={requestClose}>
            {t("cancel")}
          </Button>
          <Button
            type="submit"
            disabled={
              createTrip.isPending ||
              form.title.trim() === "" ||
              dateError !== null
            }
          >
            {createTrip.isPending ? <Spinner label={t("creating")} /> : t("create")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
