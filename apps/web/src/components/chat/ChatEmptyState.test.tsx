import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import en from "../../../messages/en.json";
import { ChatEmptyState } from "./ChatEmptyState";

function renderEmptyState(props: Parameters<typeof ChatEmptyState>[0]) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <ChatEmptyState {...props} />
    </NextIntlClientProvider>,
  );
}

const caps = en.Chat.capabilities;

describe("ChatEmptyState", () => {
  it("renders the four capability tiles with their labels and subtitles", () => {
    renderEmptyState({ onPick: () => {} });

    expect(screen.getAllByRole("button")).toHaveLength(4);
    for (const key of ["plan", "nearby", "weather", "budget"] as const) {
      expect(screen.getByText(caps[key].label)).toBeTruthy();
      expect(screen.getByText(caps[key].subtitle)).toBeTruthy();
    }
  });

  it("dispatches each tile's existing starter prompt through onPick", () => {
    const onPick = vi.fn();
    renderEmptyState({ onPick });

    fireEvent.click(screen.getByText(caps.plan.label));
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick).toHaveBeenCalledWith(en.Chat.suggestions.planWeekendPrompt);

    fireEvent.click(screen.getByText(caps.budget.label));
    expect(onPick).toHaveBeenLastCalledWith(
      en.Chat.suggestions.checkBudgetPrompt,
    );
  });

  it("renders tiles inert when disabled", () => {
    const onPick = vi.fn();
    renderEmptyState({ onPick, disabled: true });

    const tiles = screen.getAllByRole("button");
    expect(tiles).toHaveLength(4);
    for (const tile of tiles) {
      expect(tile).toBeDisabled();
    }

    fireEvent.click(screen.getByText(caps.plan.label));
    expect(onPick).not.toHaveBeenCalled();
  });
});
