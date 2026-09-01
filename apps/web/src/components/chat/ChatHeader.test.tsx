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

describe("ChatHeader — status pill", () => {
  it.each(["ready", "working", "waiting"] as const)(
    "renders a single named, polite status pill for %s",
    (status) => {
      render(<ChatHeader {...baseProps} status={status} />);
      const pill = screen.getByRole("status");
      expect(pill).toHaveAttribute("aria-live", "polite");
      const label = { ready: "statusReady", working: "statusWorking", waiting: "statusWaiting" }[
        status
      ];
      expect(pill).toHaveTextContent(label);
    },
  );
});

describe("ChatHeader — controls stay reachable by name", () => {
  it("keeps settings, expand and close accessible names in docked mode", () => {
    render(<ChatHeader {...baseProps} status="ready" />);
    expect(screen.getByLabelText("settingsMenu")).toBeInTheDocument();
    expect(screen.getByLabelText("expandPanel")).toBeInTheDocument();
    expect(screen.getByLabelText("closeAssistant")).toBeInTheDocument();
  });

  it("labels the toggle shrinkPanel when fullscreen", () => {
    render(<ChatHeader {...baseProps} status="ready" fullscreen />);
    expect(screen.getByLabelText("shrinkPanel")).toBeInTheDocument();
  });
});

describe("ChatHeader — compact mode", () => {
  it("hides the expand toggle but keeps close reachable", () => {
    render(<ChatHeader {...baseProps} status="ready" isCompact />);
    expect(screen.queryByLabelText("expandPanel")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("shrinkPanel")).not.toBeInTheDocument();
    expect(screen.getByLabelText("closeAssistant")).toBeInTheDocument();
  });

  it("gives the compact close button a ≥44px hit target", () => {
    render(<ChatHeader {...baseProps} status="ready" isCompact />);
    expect(screen.getByLabelText("closeAssistant").className).toMatch(/h-11 w-11/);
  });
});
