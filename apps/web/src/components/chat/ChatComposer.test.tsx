import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

import { ChatComposer } from "./ChatComposer";

describe("ChatComposer — disabled while streaming", () => {
  it("disables the textarea and send button when disabled", () => {
    render(
      <ChatComposer
        disabled
        onSend={vi.fn()}
        isStreaming={false}
        onStop={vi.fn()}
      />,
    );
    expect(
      (screen.getByLabelText("composerAriaLabel") as HTMLTextAreaElement)
        .disabled,
    ).toBe(true);
    expect(
      (screen.getByLabelText("sendMessage") as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("enables the textarea when not disabled", () => {
    render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        isStreaming={false}
        onStop={vi.fn()}
      />,
    );
    expect(
      (screen.getByLabelText("composerAriaLabel") as HTMLTextAreaElement)
        .disabled,
    ).toBe(false);
  });
});

describe("ChatComposer — suggestions rail", () => {
  it("renders the suggestions slot inside the composer form, above the input", () => {
    render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        isStreaming={false}
        onStop={vi.fn()}
        suggestions={<button type="button">a chip</button>}
      />,
    );
    const form = screen.getByLabelText("composerAriaLabel").closest("form");
    const chip = screen.getByText("a chip");
    // Chip lives inside the composer's own container.
    expect(form).toContainElement(chip);
    // ...and precedes the textarea (rendered above the input row).
    const textarea = screen.getByLabelText("composerAriaLabel");
    expect(
      chip.compareDocumentPosition(textarea) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("does not render a rail when no suggestions slot is passed", () => {
    render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        isStreaming={false}
        onStop={vi.fn()}
      />,
    );
    // Only the send button exists; no chip buttons.
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("dispatches a chip's action without affecting the input draft", () => {
    const onPick = vi.fn();
    render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        isStreaming={false}
        onStop={vi.fn()}
        suggestions={
          <button type="button" onClick={() => onPick("go")}>
            a chip
          </button>
        }
      />,
    );
    fireEvent.click(screen.getByText("a chip"));
    expect(onPick).toHaveBeenCalledWith("go");
    expect(
      (screen.getByLabelText("composerAriaLabel") as HTMLTextAreaElement).value,
    ).toBe("");
  });
});

describe("ChatComposer — keyboard send unchanged", () => {
  it("Enter sends the trimmed draft and clears it", () => {
    const onSend = vi.fn();
    render(
      <ChatComposer
        disabled={false}
        onSend={onSend}
        isStreaming={false}
        onStop={vi.fn()}
      />,
    );
    const textarea = screen.getByLabelText(
      "composerAriaLabel",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "  hello  " } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("hello");
    expect(textarea.value).toBe("");
  });

  it("Shift+Enter does not send (newline)", () => {
    const onSend = vi.fn();
    render(
      <ChatComposer
        disabled={false}
        onSend={onSend}
        isStreaming={false}
        onStop={vi.fn()}
      />,
    );
    const textarea = screen.getByLabelText("composerAriaLabel");
    fireEvent.change(textarea, { target: { value: "line" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });
});

describe("ChatComposer — Stop button while streaming", () => {
  it("swaps the send button to a Stop control that stays clickable and calls onStop", () => {
    const onSend = vi.fn();
    const onStop = vi.fn();
    // `disabled` (inputBlocked) is true while streaming — the Stop button must
    // stay clickable regardless.
    render(
      <ChatComposer
        disabled
        onSend={onSend}
        isStreaming
        onStop={onStop}
      />,
    );
    // Send affordance is gone; Stop affordance is present and enabled.
    expect(screen.queryByLabelText("sendMessage")).toBeNull();
    const stopButton = screen.getByLabelText("stopMessage") as HTMLButtonElement;
    expect(stopButton.disabled).toBe(false);
    expect(stopButton.getAttribute("type")).toBe("button");
    fireEvent.click(stopButton);
    expect(onStop).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();
  });
});
