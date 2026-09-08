import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ tripId: "trip-1" }),
}));

const h = vi.hoisted(() => ({ useTrip: vi.fn() }));

vi.mock("@/lib/query/trips", () => ({
  useTrip: h.useTrip,
}));

import TripDetailPage from "./page";

describe("TripDetailPage", () => {
  it("renders the tab-bar shape and an sr-only live region while pending", () => {
    h.useTrip.mockReturnValue({ data: undefined, isPending: true, isError: false });
    render(<TripDetailPage />);

    expect(screen.getByTestId("trip-detail-page-skeleton")).toBeTruthy();

    const status = screen.getByRole("status");
    expect(status.className).toContain("sr-only");
    expect(status.textContent).toBe("loadingLabel");
  });

  it("keeps the sr-only live region mounted (with empty text) once not pending", () => {
    // Use the error branch rather than the success branch — the success
    // branch renders TripHeader/tab components with their own data
    // dependencies unrelated to this live-region assertion.
    h.useTrip.mockReturnValue({ data: undefined, isPending: false, isError: true });
    render(<TripDetailPage />);

    const status = screen.getByRole("status");
    expect(status.className).toContain("sr-only");
    expect(status.textContent).toBe("");
  });
});
