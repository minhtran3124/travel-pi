"use client";

import { useTranslations } from "next-intl";

type ChatSuggestionsProps = {
  suggestions: string[];
  onPick: (text: string) => void;
  disabled?: boolean;
};

export function ChatSuggestions({
  suggestions,
  onPick,
  disabled,
}: ChatSuggestionsProps) {
  const t = useTranslations("Chat");

  if (suggestions.length === 0) return null;

  const items = suggestions.map((key) => ({
    key,
    label: t(`followups.${key}.label`),
    prompt: t(`followups.${key}.prompt`),
  }));

  // Bare row of chips — no band. Meant to ride the composer's scrollable rail,
  // so each chip keeps its width (`shrink-0`) and never wraps to a second row.
  return (
    <>
      {items.map(({ key, label, prompt }) => (
        <button
          key={key}
          type="button"
          disabled={disabled}
          onClick={() => onPick(prompt)}
          className="shrink-0 whitespace-nowrap rounded-pill bg-panel-raised px-md py-1 text-xs font-medium text-ink transition duration-150 hover:-translate-y-0.5 hover:bg-lime-soft active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
        >
          {label}
        </button>
      ))}
    </>
  );
}
