import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HotelsPanel } from "./HotelsPanel";
import type { HotelsPanelData } from "@/lib/stream/panel";

const DATA: HotelsPanelData = {
  city: "Da Nang",
  check_in: "2027-04-10",
  check_out: "2027-04-14",
  nights: 4,
  rooms: 1,
  results_count: 2,
  cheapest_total: 320,
  hotels: [
    { id: "h1", short_code: "HTL-AA11BB", name: "Grand Da Nang Hotel", star_rating: 4,
      price_per_night: 120, currency: "USD", total_price: 480, available: true,
      available_rooms: 10, rating: 4.5, review_count: 842, amenities: ["wifi", "pool", "breakfast"] },
    { id: "h2", short_code: "HTL-CC33DD", name: "Seaside Resort", star_rating: 5,
      price_per_night: 80, currency: "USD", total_price: 320, available: true,
      available_rooms: 5, rating: 4.8, review_count: 311, amenities: ["wifi", "pool", "spa", "breakfast"] },
  ],
};

describe("HotelsPanel", () => {
  it("renders a row per hotel and the header", () => {
    render(<HotelsPanel data={DATA} />);
    expect(screen.getByText(/2 results/i)).toBeInTheDocument();
    // Hotel name sits in a mixed text node — match with a regex (repo convention).
    expect(screen.getByText(/Grand Da Nang Hotel/)).toBeInTheDocument();
    expect(screen.getByText(/Seaside Resort/)).toBeInTheDocument();
  });

  it("expands a row on click to reveal detail", () => {
    render(<HotelsPanel data={DATA} />);
    expect(screen.queryByText(/HTL-AA11BB/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/Grand Da Nang Hotel/));
    expect(screen.getByText(/HTL-AA11BB/)).toBeInTheDocument(); // short code in detail
  });
});
