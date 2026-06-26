"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Meter } from "@/components/ui/Meter";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import {
  useDeleteExpense,
  useExpenseSummary,
  useExpenses,
  type Expense,
  type ExpenseCategory,
  type ExpenseFilters,
} from "@/lib/query/expenses";

import { ExpenseForm } from "./ExpenseForm";

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

type Formatter = ReturnType<typeof useFormatter>;

function usd(format: Formatter, value: number): string {
  return format.number(value, "usd");
}

function money(format: Formatter, amount: number, currency: string): string {
  try {
    return format.number(amount, { style: "currency", currency });
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function CategoryPill({ category }: { category: ExpenseCategory }) {
  const t = useTranslations("Expenses");
  return (
    <span className="inline-flex items-center rounded-pill bg-panel-raised px-sm py-px text-xs font-bold capitalize text-muted">
      {t(`categories.${category}`)}
    </span>
  );
}

function SummaryPanel({ tripId }: { tripId: string }) {
  const t = useTranslations("Expenses");
  const tCommon = useTranslations("Common");
  const format = useFormatter();
  const { data, isPending } = useExpenseSummary(tripId);

  if (isPending) {
    return (
      <Card className="flex items-center gap-sm text-sm text-muted">
        <Spinner label={t("summary.loadingLabel")} />
        <span>{t("summary.loading")}</span>
      </Card>
    );
  }
  if (!data) return null;

  const { budget } = data;

  return (
    <Card className="flex flex-col gap-md">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-extrabold text-ink">{t("summary.title")}</h3>
        <span className="text-sm tabular-nums text-muted">
          {t("summary.entryCount", { count: data.expense_count })} ·{" "}
          {usd(format, data.total_usd)}
        </span>
      </div>

      <div className="flex flex-col gap-xs">
        <p className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
          {t("summary.byCategory")}
        </p>
        {data.by_category.length === 0 ? (
          <p className="text-sm text-muted">{t("summary.noSpend")}</p>
        ) : (
          data.by_category.map((c) => (
            <div
              key={c.category}
              className="flex items-center justify-between text-sm"
            >
              <CategoryPill category={c.category} />
              <span className="tabular-nums text-ink">
                {usd(format, c.total_usd)}{" "}
                <span className="text-muted">({c.count})</span>
              </span>
            </div>
          ))
        )}
      </div>

      <div className="flex flex-col gap-xs">
        <p className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
          {t("summary.byCurrency")}
        </p>
        {data.by_currency.length === 0 ? (
          <p className="text-sm text-muted">{t("summary.noSpend")}</p>
        ) : (
          data.by_currency.map((c) => (
            <div
              key={c.currency}
              className="flex items-center justify-between text-sm"
            >
              <span className="font-bold text-ink">{c.currency}</span>
              <span className="tabular-nums text-muted">
                {money(format, c.total_original, c.currency)} → {usd(format, c.total_usd)}
              </span>
            </div>
          ))
        )}
      </div>

      <div className="flex flex-col gap-xs border-t border-line pt-sm">
        <p className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
          {t("summary.budgetActuals")}
        </p>
        <div className="flex justify-between text-sm">
          <span className="text-muted">{t("summary.booked")}</span>
          <span className="tabular-nums text-ink">
            {usd(format, budget.booked_spent)}
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted">{t("summary.expenses")}</span>
          <span className="tabular-nums text-ink">
            {usd(format, budget.expense_spent)}
          </span>
        </div>
        <div className="flex justify-between text-sm font-bold">
          <span className="text-ink">{t("summary.totalSpent")}</span>
          <span className="tabular-nums text-ink">
            {usd(format, budget.total_spent)}
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted">{t("summary.cap")}</span>
          <span className="tabular-nums text-muted">
            {budget.total_cap == null ? tCommon("notAvailable") : usd(format, budget.total_cap)}
          </span>
        </div>
        <div className="flex justify-between text-sm font-bold">
          <span className="text-ink">{t("summary.remaining")}</span>
          <span
            className={`tabular-nums ${
              budget.over_budget ? "text-status-cancelled" : "text-ink"
            }`}
          >
            {budget.total_remaining == null
              ? tCommon("notAvailable")
              : usd(format, budget.total_remaining)}
          </span>
        </div>
        {budget.total_cap != null ? (
          <Meter value={budget.total_spent} max={budget.total_cap} className="mt-xs" />
        ) : null}
        {budget.over_budget ? (
          <p
            role="alert"
            className="text-sm font-bold text-status-cancelled"
          >
            {t("summary.overBudget")}
          </p>
        ) : null}
      </div>
    </Card>
  );
}

function LedgerRow({
  expense,
  onEdit,
  onDelete,
  deleting,
}: {
  expense: Expense;
  onEdit: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  const t = useTranslations("Expenses");
  const format = useFormatter();
  return (
    <div className="flex items-center justify-between gap-md border-b border-line py-sm last:border-b-0">
      <div className="flex min-w-0 flex-col gap-xs">
        <div className="flex items-center gap-sm">
          <CategoryPill category={expense.category} />
          <span className="truncate text-sm text-ink">
            {expense.description ?? expense.short_code}
          </span>
        </div>
        <span className="text-xs text-muted">
          {expense.occurred_at
            ? expense.occurred_at.slice(0, 10)
            : expense.created_at.slice(0, 10)}
        </span>
      </div>
      <div className="flex items-center gap-md">
        <div className="text-right">
          <div className="text-sm tabular-nums text-ink">
            {money(format, expense.amount, expense.currency)}
          </div>
          <div className="text-xs tabular-nums text-muted">
            {usd(format, expense.amount_usd)}
          </div>
        </div>
        <div className="flex gap-xs">
          <Button variant="ghost" onClick={onEdit}>
            {t("edit")}
          </Button>
          <Button variant="ghost" onClick={onDelete} disabled={deleting}>
            {deleting ? t("deleting") : t("delete")}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ExpensesTab({ tripId }: { tripId: string }) {
  const t = useTranslations("Expenses");
  const [filters, setFilters] = useState<ExpenseFilters>({});
  const { data, isPending, isError } = useExpenses(
    tripId,
    Object.keys(filters).length > 0 ? filters : undefined,
  );
  const deleteExpense = useDeleteExpense(tripId);

  // null = closed; "new" = add form; an Expense = edit that entry.
  const [formState, setFormState] = useState<"new" | Expense | null>(null);

  function setFilter(key: keyof ExpenseFilters, value: string) {
    setFilters((f) => {
      const next = { ...f };
      if (value === "") delete next[key];
      else if (key === "category") next.category = value as ExpenseCategory;
      else next[key] = value as never;
      return next;
    });
  }

  return (
    <section className="flex flex-col gap-md">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-extrabold text-ink">{t("title")}</h2>
        <Button onClick={() => setFormState("new")}>{t("addExpense")}</Button>
      </div>

      <div className="flex flex-wrap items-end gap-sm">
        <Select
          id="expense-filter-category"
          label={t("filterCategory")}
          value={filters.category ?? ""}
          onChange={(e) => setFilter("category", e.target.value)}
        >
          <option value="">{t("filterAll")}</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(`categories.${c}`)}
            </option>
          ))}
        </Select>
        <Field
          id="expense-filter-from"
          label={t("filterFrom")}
          type="date"
          value={filters.date_from ?? ""}
          onChange={(e) => setFilter("date_from", e.target.value)}
        />
        <Field
          id="expense-filter-to"
          label={t("filterTo")}
          type="date"
          value={filters.date_to ?? ""}
          onChange={(e) => setFilter("date_to", e.target.value)}
        />
      </div>

      <div className="grid gap-md md:grid-cols-[2fr_1fr]">
        <Card className="flex flex-col">
          {isPending ? (
            <div className="flex items-center gap-sm text-sm text-muted">
              <Spinner label={t("loadingLabel")} />
              <span>{t("loading")}</span>
            </div>
          ) : isError || !data ? (
            <EmptyState
              icon="💸"
              title={t("errorTitle")}
              hint={t("errorHint")}
            />
          ) : data.results.length === 0 ? (
            <EmptyState
              icon="🧾"
              title={t("emptyTitle")}
              hint={t("emptyHint")}
              action={
                <Button onClick={() => setFormState("new")}>
                  {t("addExpense")}
                </Button>
              }
            />
          ) : (
            data.results.map((e) => (
              <LedgerRow
                key={e.id}
                expense={e}
                onEdit={() => setFormState(e)}
                onDelete={() => deleteExpense.mutate(e.id)}
                deleting={
                  deleteExpense.isPending &&
                  deleteExpense.variables === e.id
                }
              />
            ))
          )}
        </Card>

        <SummaryPanel tripId={tripId} />
      </div>

      <Modal
        open={formState !== null}
        onClose={() => setFormState(null)}
        title={formState === "new" ? t("modalAddTitle") : t("modalEditTitle")}
      >
        {formState !== null ? (
          <ExpenseForm
            tripId={tripId}
            expense={formState === "new" ? undefined : formState}
            onDone={() => setFormState(null)}
          />
        ) : null}
      </Modal>
    </section>
  );
}
