import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const h = vi.hoisted(() => ({ useTrips: vi.fn() }));

vi.mock("@/lib/query/trips", () => ({
  useTrips: h.useTrips,
  useCreateTrip: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    reset: vi.fn(),
  }),
}));

import TripsPage from "./page";

describe("TripsPage", () => {
  it("renders the grid skeleton and an sr-only live region while pending", () => {
    h.useTrips.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      refetch: vi.fn(),
    });
    render(<TripsPage />);

    expect(screen.getByTestId("trips-grid-skeleton")).toBeTruthy();

    const status = screen.getByRole("status");
    expect(status.className).toContain("sr-only");
    expect(status.textContent).toBe("loadingTripsStatus");
  });

  it("keeps the sr-only live region mounted (with empty text) once loaded", () => {
    h.useTrips.mockReturnValue({
      data: { results: [] },
      isPending: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(<TripsPage />);

    const status = screen.getByRole("status");
    expect(status.className).toContain("sr-only");
    expect(status.textContent).toBe("");
  });
});
