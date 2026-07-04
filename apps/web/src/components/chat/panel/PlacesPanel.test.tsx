import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlacesPanel } from "./PlacesPanel";
import type { PlacesPanelData } from "@/lib/stream/panel";

const DATA: PlacesPanelData = {
  city: "Da Nang",
  category: "landmark",
  results_count: 2,
  places: [
    { id: "p1", name: "Marble Mountains", city: "Da Nang", country: "Vietnam",
      category: "landmark", description: "Cluster of limestone hills with caves and temples.",
      address: "52 Huyen Tran Cong Chua", rating: 4.6, review_count: 1204, price_level: 1,
      opening_hours: "Mon-Sun 07:00-17:30", image_url: "https://example.com/marble.jpg",
      tags: ["outdoor", "scenic"], is_recommended: true },
    { id: "p2", name: "Han Market", city: "Da Nang", country: "Vietnam",
      category: "shopping", description: "Bustling local market for food and souvenirs.",
      address: "119 Tran Phu", rating: 4.2, review_count: 388, price_level: 2,
      opening_hours: null, image_url: "https://example.com/han.jpg",
      tags: ["market", "food"], is_recommended: false },
  ],
};

describe("PlacesPanel", () => {
  it("renders a row per place and the header", () => {
    render(<PlacesPanel data={DATA} />);
    expect(screen.getByText(/2 results/i)).toBeInTheDocument();
    // Place name sits in a mixed text node — match with a regex (repo convention).
    expect(screen.getByText(/Marble Mountains/)).toBeInTheDocument();
    expect(screen.getByText(/Han Market/)).toBeInTheDocument();
  });

  it("renders a thumbnail per place", () => {
    render(<PlacesPanel data={DATA} />);
    // one img per place, alt = place name
    expect(screen.getByAltText("Marble Mountains")).toBeInTheDocument();
    expect(screen.getByAltText("Han Market")).toBeInTheDocument();
  });

  it("expands a row on click to reveal detail", () => {
    render(<PlacesPanel data={DATA} />);
    // description + review count only appear in the expanded detail, not the collapsed row
    expect(screen.queryByText(/1204 reviews/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Cluster of limestone hills/),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/Marble Mountains/));
    expect(screen.getByText(/1204 reviews/)).toBeInTheDocument();
    expect(screen.getByText(/Cluster of limestone hills/)).toBeInTheDocument();
  });

  it("only capitalizes the category detail, not the composite rating/reviews text", () => {
    const { container } = render(<PlacesPanel data={DATA} />);
    fireEvent.click(screen.getByText(/Marble Mountains/));
    const ratingDetail = screen.getByText(/1204 reviews/);
    expect(ratingDetail.className).not.toMatch(/\bcapitalize\b/);
    const categoryDetail = container.querySelector("dd.capitalize");
    expect(categoryDetail).not.toBeNull();
    expect(categoryDetail?.textContent).toBe("landmark");
  });
});
