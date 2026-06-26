import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("renders its label", () => {
    render(<Button>Book trip</Button>);
    expect(screen.getByText("Book trip")).toBeInTheDocument();
  });

  it("has role=button", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
  });

  it("applies the primary variant class by default", () => {
    render(<Button>Primary</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-coral-deep");
  });

  it("applies the ghost variant class", () => {
    render(<Button variant="ghost">Ghost</Button>);
    const btn = screen.getByRole("button");
    expect(btn).not.toHaveClass("bg-coral-deep");
    expect(btn).toHaveClass("border");
  });

  it("fires onClick", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Tap</Button>);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("forwards button HTML attributes", () => {
    render(
      <Button type="submit" disabled>
        Submit
      </Button>,
    );
    const btn = screen.getByRole("button") as HTMLButtonElement;
    expect(btn.type).toBe("submit");
    expect(btn.disabled).toBe(true);
  });
});
