import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

import { ChatComposer } from "./ChatComposer";

describe("ChatComposer — disabled while streaming", () => {
  it("disables the textarea and send button when disabled", () => {
    render(<ChatComposer disabled onSend={vi.fn()} />);
    expect(
      (screen.getByLabelText("composerAriaLabel") as HTMLTextAreaElement)
        .disabled,
    ).toBe(true);
    expect(
      (screen.getByLabelText("sendMessage") as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("enables the textarea when not disabled", () => {
    render(<ChatComposer disabled={false} onSend={vi.fn()} />);
    expect(
      (screen.getByLabelText("composerAriaLabel") as HTMLTextAreaElement)
        .disabled,
    ).toBe(false);
  });
});
