import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({
  useTranslations: () => (k: string) => k,
  useFormatter: () => ({}),
}));

const h = vi.hoisted(() => ({
  useBookings: vi.fn(),
  useCancelBooking: vi.fn(),
}));

vi.mock("@/lib/query/bookings", () => ({
  useBookings: h.useBookings,
  useCancelBooking: h.useCancelBooking,
}));

import BookingsPage from "./page";

function setLoading() {
  h.useBookings.mockReturnValue({
    data: undefined,
    isLoading: true,
    isError: false,
  });
  h.useCancelBooking.mockReturnValue({ mutate: vi.fn(), isPending: false });
}

describe("BookingsPage loading state", () => {
  it("renders the table skeleton, no spinner, a live filter row, and an sr-only live region", () => {
    setLoading();
    render(<BookingsPage />);

    expect(screen.getByTestId("bookings-table-skeleton")).toBeInTheDocument();

    expect(
      document.querySelector(".animate-spin"),
    ).not.toBeInTheDocument();

    expect(screen.getByLabelText("searchLabel")).toBeInTheDocument();

    const status = screen.getByRole("status");
    expect(status).toHaveClass("sr-only");
  });
});
