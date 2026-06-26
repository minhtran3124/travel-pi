"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import type { TripItemKind, TripItemStatus } from "@/lib/query/items";

const KINDS: TripItemKind[] = ["place", "activity", "meal", "transport", "note"];
const STATUSES: TripItemStatus[] = [
  "pending",
  "booked",
  "constraint",
  "optional",
];

export interface ItemFormValues {
  day: number;
  kind: TripItemKind;
  status: TripItemStatus;
  title: string;
  place_id: string | null;
  start_time: string | null;
  notes: string | null;
}

export interface ItemFormProps {
  open: boolean;
  title: string;
  initial?: Partial<ItemFormValues>;
  submitting?: boolean;
  /** Surfaced as an inline notice (e.g. the 409 over-budget message). */
  notice?: string | null;
  onSubmit: (values: ItemFormValues) => void;
  onClose: () => void;
}

function trimToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function ItemForm({
  open,
  title,
  initial,
  submitting = false,
  notice,
  onSubmit,
  onClose,
}: ItemFormProps) {
  const t = useTranslations("Itinerary");
  const [day, setDay] = useState(String(initial?.day ?? 1));
  const [kind, setKind] = useState<TripItemKind>(initial?.kind ?? "place");
  const [status, setStatus] = useState<TripItemStatus>(
    initial?.status ?? "pending",
  );
  const [titleValue, setTitleValue] = useState(initial?.title ?? "");
  const [placeId, setPlaceId] = useState(initial?.place_id ?? "");
  const [startTime, setStartTime] = useState(initial?.start_time ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    onSubmit({
      day: Math.max(1, Number(day) || 1),
      kind,
      status,
      title: titleValue.trim(),
      place_id: trimToNull(placeId),
      start_time: trimToNull(startTime),
      notes: trimToNull(notes),
    });
  }

  return (
    <Modal open={open} onClose={onClose} title={title}>
      <form className="flex flex-col gap-md" onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 gap-md">
          <Field
            label={t("form.day")}
            type="number"
            min={1}
            value={day}
            onChange={(e) => setDay(e.target.value)}
            required
          />
          <Field
            label={t("form.startTime")}
            placeholder={t("form.startTimePlaceholder")}
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-md">
          <Select
            label={t("form.kind")}
            value={kind}
            onChange={(e) => setKind(e.target.value as TripItemKind)}
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`kinds.${k}`)}
              </option>
            ))}
          </Select>
          <Select
            label={t("form.status")}
            value={status}
            onChange={(e) => setStatus(e.target.value as TripItemStatus)}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`statuses.${s}`)}
              </option>
            ))}
          </Select>
        </div>

        <Field
          label={t("form.title")}
          value={titleValue}
          onChange={(e) => setTitleValue(e.target.value)}
          maxLength={200}
          required
        />

        <Field
          label={t("form.placeId")}
          value={placeId}
          onChange={(e) => setPlaceId(e.target.value)}
        />

        <Textarea
          label={t("form.notes")}
          value={notes}
          maxLength={1000}
          onChange={(e) => setNotes(e.target.value)}
        />

        {notice ? (
          <p className="rounded-sm border border-status-cancelled/40 bg-status-cancelled/10 px-sm py-xs text-sm text-status-cancelled">
            {notice}
          </p>
        ) : null}

        <div className="mt-sm flex justify-end gap-sm">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            {t("form.cancel")}
          </Button>
          <Button
            type="submit"
            disabled={submitting || titleValue.trim().length === 0}
          >
            {submitting ? t("form.saving") : t("form.save")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
