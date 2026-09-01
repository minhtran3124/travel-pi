import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

import { MessageActions } from "./MessageActions";

function mockClipboard(writeText: () => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
    writable: true,
  });
}

describe("MessageActions", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("copies the content and shows a confirmation that reverts", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn().mockResolvedValue(undefined);
    mockClipboard(writeText);

    render(<MessageActions content="hello world" />);

    // Click, then flush the writeText microtask + the state update.
    await act(async () => {
      fireEvent.click(screen.getByLabelText("actions.copy"));
      await Promise.resolve();
    });

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith("hello world");

    // Confirmation swaps in.
    expect(screen.getByLabelText("actions.copied")).toBeInTheDocument();
    expect(screen.queryByLabelText("actions.copy")).toBeNull();

    // After the reset window it reverts to the copy label.
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.getByLabelText("actions.copy")).toBeInTheDocument();
    expect(screen.queryByLabelText("actions.copied")).toBeNull();
  });

  it("fires onRegenerate when the regenerate button is clicked", () => {
    const onRegenerate = vi.fn();
    render(<MessageActions content="x" onRegenerate={onRegenerate} />);

    fireEvent.click(screen.getByLabelText("actions.regenerate"));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });

  it("omits the regenerate button when no callback is supplied", () => {
    render(<MessageActions content="x" />);
    expect(screen.queryByLabelText("actions.regenerate")).toBeNull();
  });

  it("renders both buttons inert when disabled", () => {
    const onRegenerate = vi.fn();
    render(
      <MessageActions content="x" onRegenerate={onRegenerate} disabled />,
    );

    const copy = screen.getByLabelText("actions.copy");
    const regenerate = screen.getByLabelText("actions.regenerate");
    expect(copy).toBeDisabled();
    expect(regenerate).toBeDisabled();
  });

  it("does not throw when the clipboard API is unavailable", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
      writable: true,
    });

    render(<MessageActions content="x" />);
    expect(() =>
      fireEvent.click(screen.getByLabelText("actions.copy")),
    ).not.toThrow();

    // No confirmation appears; the copy label stays.
    await waitFor(() => {
      expect(screen.getByLabelText("actions.copy")).toBeInTheDocument();
    });
    expect(screen.queryByLabelText("actions.copied")).toBeNull();
  });

  it("does not throw when clipboard.writeText rejects", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    mockClipboard(writeText);

    render(<MessageActions content="x" />);
    fireEvent.click(screen.getByLabelText("actions.copy"));

    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(screen.queryByLabelText("actions.copied")).toBeNull();
  });
});
