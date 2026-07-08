import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

import { ConfirmDialog } from "./ConfirmDialog";

function setup(open = true) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      open={open}
      title="New conversation"
      message="This clears the current chat."
      confirmLabel="Start new"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />,
  );
  return { onConfirm, onCancel };
}

describe("ConfirmDialog", () => {
  it("renders nothing when closed", () => {
    setup(false);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows title, message and both actions when open", () => {
    setup();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("This clears the current chat.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start new" })).toBeInTheDocument();
    // cancelLabel omitted → falls back to the shared Common.cancel key.
    expect(screen.getByRole("button", { name: "cancel" })).toBeInTheDocument();
  });

  it("fires onConfirm on the affirmative action", () => {
    const { onConfirm, onCancel } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Start new" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("fires onCancel on the cancel action", () => {
    const { onConfirm, onCancel } = setup();
    fireEvent.click(screen.getByRole("button", { name: "cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
