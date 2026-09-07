import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

import { ChatSuggestions } from "./ChatSuggestions";

describe("ChatSuggestions", () => {
  it("renders a button per suggestion key", () => {
    render(
      <ChatSuggestions
        suggestions={["booking.otherOptions", "booking.bookThis"]}
        onPick={() => {}}
      />,
    );
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("calls onPick once with the resolved prompt on click", () => {
    const onPick = vi.fn();
    render(
      <ChatSuggestions
        suggestions={["booking.otherOptions", "booking.bookThis"]}
        onPick={onPick}
      />,
    );
    fireEvent.click(screen.getAllByRole("button")[0]);
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick).toHaveBeenCalledWith("followups.booking.otherOptions.prompt");
  });

  it("renders nothing when there are no suggestions", () => {
    const { container } = render(
      <ChatSuggestions suggestions={[]} onPick={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders a bare row of chips — no border/background band", () => {
    const { container } = render(
      <ChatSuggestions suggestions={["booking.bookThis"]} onPick={() => {}} />,
    );
    // Chips are direct children (a bare row for the composer rail), not wrapped
    // in a bordered band element.
    expect(container.firstElementChild?.tagName).toBe("BUTTON");
    expect(container.querySelector(".border-t")).toBeNull();
    // Borderless chips — separation comes from the raised surface, not a line.
    expect(screen.getByRole("button").className).not.toContain("border-line");
    // Each chip keeps its width in the scrollable rail.
    expect(screen.getByRole("button").className).toContain("shrink-0");
  });
});
