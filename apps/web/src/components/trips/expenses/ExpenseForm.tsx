"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import {
  useAddExpense,
  useUpdateExpense,
  type Expense,
  type ExpenseCategory,
} from "@/lib/query/expenses";

const CATEGORIES: ExpenseCategory[] = [
  "food",
  "transport",
  "accommodation",
  "activities",
  "shopping",
  "entertainment",
  "health",
  "other",
];

// `occurred_at` is a full ISO datetime; the form edits the date portion only.
function toDateInput(iso: string | null | undefined): string {
  if (!iso) return "";
  return iso.slice(0, 10);
}

export function ExpenseForm({
  tripId,
  expense,
  onDone,
}: {
  tripId: string;
  expense?: Expense;
  onDone: () => void;
}) {
  const t = useTranslations("Expenses");
  const add = useAddExpense(tripId);
  const update = useUpdateExpense(tripId);
  const isEdit = expense !== undefined;

  const [category, setCategory] = useState<ExpenseCategory>(
    expense?.category ?? "food",
  );
  const [amount, setAmount] = useState(
    expense ? String(expense.amount) : "",
  );
  const [currency, setCurrency] = useState(expense?.currency ?? "USD");
  const [description, setDescription] = useState(expense?.description ?? "");
  const [occurredAt, setOccurredAt] = useState(
    toDateInput(expense?.occurred_at),
  );

  const pending = add.isPending || update.isPending;
  const errored = add.isError || update.isError;
  const amountNum = Number(amount);
  const valid =
    amount.trim() !== "" &&
    Number.isFinite(amountNum) &&
    amountNum > 0 &&
    currency.trim() !== "";

  function submit() {
    if (!valid) return;
    const occurred = occurredAt.trim() === "" ? null : occurredAt;
    if (isEdit) {
      update.mutate(
        {
          id: expense.id,
          body: {
            category,
            amount: amountNum,
            currency: currency.trim().toUpperCase(),
            description: description.trim() === "" ? null : description,
            occurred_at: occurred,
          },
        },
        { onSuccess: onDone },
      );
    } else {
      add.mutate(
        {
          category,
          amount: amountNum,
          currency: currency.trim().toUpperCase(),
          description: description.trim() === "" ? null : description,
          occurred_at: occurred,
        },
        { onSuccess: onDone },
      );
    }
  }

  return (
    <div className="flex flex-col gap-md">
      <Select
        label={t("form.category")}
        value={category}
        onChange={(e) => setCategory(e.target.value as ExpenseCategory)}
      >
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {t(`categories.${c}`)}
          </option>
        ))}
      </Select>

      <div className="grid grid-cols-2 gap-sm">
        <Field
          label={t("form.amount")}
          type="number"
          min={0}
          step="0.01"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <Field
          label={t("form.currency")}
          value={currency}
          maxLength={3}
          onChange={(e) => setCurrency(e.target.value)}
        />
      </div>

      <Field
        label={t("form.description")}
        value={description}
        placeholder={t("form.descriptionPlaceholder")}
        onChange={(e) => setDescription(e.target.value)}
      />

      <Field
        label={t("form.date")}
        type="date"
        value={occurredAt}
        onChange={(e) => setOccurredAt(e.target.value)}
      />

      {errored ? (
        <p className="text-sm text-status-cancelled">
          {t("form.saveError")}
        </p>
      ) : null}

      <div className="flex justify-end gap-sm">
        <Button variant="ghost" onClick={onDone}>
          {t("form.cancel")}
        </Button>
        <Button onClick={submit} disabled={!valid || pending}>
          {pending ? t("form.saving") : isEdit ? t("form.saveChanges") : t("form.add")}
        </Button>
      </div>
    </div>
  );
}
