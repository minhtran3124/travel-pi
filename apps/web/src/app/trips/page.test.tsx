import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/query/trips", () => ({
  useTrips: () => ({
    data: undefined,
    isPending: true,
    isError: false,
    refetch: vi.fn(),
  }),
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
    render(<TripsPage />);

    expect(screen.getByTestId("trips-grid-skeleton")).toBeTruthy();

    const status = screen.getByRole("status");
    expect(status.className).toContain("sr-only");
  });
});
