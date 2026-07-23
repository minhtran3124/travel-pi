import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

import { ChatSettingsMenu } from "./ChatSettingsMenu";

describe("ChatSettingsMenu", () => {
  it("starts closed — no menu item rendered", () => {
    render(<ChatSettingsMenu onNewConversation={vi.fn()} />);
    expect(screen.queryByRole("menuitem")).toBeNull();
  });

  it("opens the menu when the trigger is clicked", () => {
    render(<ChatSettingsMenu onNewConversation={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("settingsMenu"));
    expect(screen.getByRole("menuitem")).toBeTruthy();
  });

  it("fires onNewConversation when the item is chosen", () => {
    const onNewConversation = vi.fn();
    render(<ChatSettingsMenu onNewConversation={onNewConversation} />);
    fireEvent.click(screen.getByLabelText("settingsMenu"));
    fireEvent.click(screen.getByRole("menuitem"));
    expect(onNewConversation).toHaveBeenCalledTimes(1);
  });

  it("disables the trigger when disabled", () => {
    render(<ChatSettingsMenu onNewConversation={vi.fn()} disabled />);
    expect(
      (screen.getByLabelText("settingsMenu") as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});
