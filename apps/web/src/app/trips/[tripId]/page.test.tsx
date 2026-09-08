import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ tripId: "trip-1" }),
}));
vi.mock("@/lib/query/trips", () => ({
  useTrip: () => ({ data: undefined, isPending: true, isError: false }),
}));

import TripDetailPage from "./page";

describe("TripDetailPage", () => {
  it("renders the tab-bar shape and an sr-only live region while pending", () => {
    render(<TripDetailPage />);

    expect(screen.getByTestId("trip-detail-page-skeleton")).toBeTruthy();

    const status = screen.getByRole("status");
    expect(status.className).toContain("sr-only");
    expect(status.textContent).toBe("loadingLabel");
  });
});
