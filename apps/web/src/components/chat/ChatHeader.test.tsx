import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

import { ChatHeader } from "./ChatHeader";

const baseProps = {
  fullscreen: false,
  onToggleFullscreen: vi.fn(),
  onClose: vi.fn(),
  onNewConversation: vi.fn(),
};

describe("ChatHeader — settings menu safety", () => {
  it("enables the settings gear when the agent is ready", () => {
    render(<ChatHeader {...baseProps} status="ready" />);
    expect(
      (screen.getByLabelText("settingsMenu") as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  // Disabling the gear mid-turn is what prevents a New-conversation reset from
  // racing an in-flight stream (whose `start` event would restore the old id).
  it.each(["working", "waiting"] as const)(
    "disables the settings gear while %s",
    (status) => {
      render(<ChatHeader {...baseProps} status={status} />);
      expect(
        (screen.getByLabelText("settingsMenu") as HTMLButtonElement).disabled,
      ).toBe(true);
    },
  );
});
