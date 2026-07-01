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
    { id: "h1", image_url: "https://example.com/grand.jpg", name: "Grand Da Nang Hotel", star_rating: 4,
      price_per_night: 120, currency: "USD", total_price: 480, available: true,
      available_rooms: 10, rating: 4.5, review_count: 842, amenities: ["wifi", "pool", "breakfast"] },
    { id: "h2", image_url: "https://example.com/seaside.jpg", name: "Seaside Resort", star_rating: 5,
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

  it("renders a thumbnail per hotel", () => {
    render(<HotelsPanel data={DATA} />);
    // one img per hotel, alt = hotel name
    expect(screen.getByAltText("Grand Da Nang Hotel")).toBeInTheDocument();
    expect(screen.getByAltText("Seaside Resort")).toBeInTheDocument();
  });

  it("expands a row on click to reveal detail", () => {
    render(<HotelsPanel data={DATA} />);
    // review count only appears in the expanded detail, not the collapsed row
    expect(screen.queryByText(/842 reviews/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/Grand Da Nang Hotel/));
    expect(screen.getByText(/842 reviews/)).toBeInTheDocument();
  });
});

