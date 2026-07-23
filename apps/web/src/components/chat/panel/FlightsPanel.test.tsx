// A non-UTC zone (Node re-reads TZ on assignment): under UTC a timezone-shift
// regression in the rendered times would be invisible.
process.env.TZ = "Asia/Ho_Chi_Minh";

import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { FlightsPanel } from "./FlightsPanel";
import { PanelIntlProvider } from "./PanelIntlProvider";
import type { FlightsPanelData } from "@/lib/stream/panel";

// Panels read STATIC labels via `useTranslations`, so they must render inside a
// PanelIntlProvider (the streamed-language provider used in production).
const Intl = ({ children }: { children: ReactNode }) => (
  <PanelIntlProvider language="en">{children}</PanelIntlProvider>
);

// Times are naive wall-clock strings — exactly what the API serves (no offset).
const DATA: FlightsPanelData = {
  origin: "HAN",
  destination: "SGN",
  departure_date: "2027-03-15",
  results_count: 2,
  cheapest_price: 76,
  flights: [
    { id: "1", flight_number: "VJ155", airline_name: "VietJet Air", airline_code: "VJ",
      origin: "HAN", destination: "SGN", departure_time: "2027-03-15T09:00:00",
      arrival_time: "2027-03-15T11:15:00", duration_minutes: 135, stops: 0,
      seats_available: 5, price: 98, currency: "USD" },
    { id: "2", flight_number: "VJ179", airline_name: "VietJet Air", airline_code: "VJ",
      origin: "HAN", destination: "SGN", departure_time: "2027-03-15T20:30:00",
      arrival_time: "2027-03-15T23:05:00", duration_minutes: 155, stops: 1,
      seats_available: 3, price: 76, currency: "USD" },
  ],
};

describe("FlightsPanel", () => {
  it("renders a row per flight and the header count", () => {
    render(<FlightsPanel data={DATA} />, { wrapper: Intl });
    expect(screen.getByText(/2 results/i)).toBeInTheDocument();
    // Flight number sits in a mixed text node ("VietJet Air VJ155 · nonstop · 5 left"),
    // so match with a regex — the repo convention (see RoutePanel.test.tsx).
    expect(screen.getByText(/VJ155/)).toBeInTheDocument();
    expect(screen.getByText(/VJ179/)).toBeInTheDocument();
  });

  it("renders the airport wall-clock times, unshifted by the viewer's timezone", () => {
    render(<FlightsPanel data={DATA} />, { wrapper: Intl });
    expect(screen.getByText(/09:00 → 11:15/)).toBeInTheDocument();
    expect(screen.getByText(/20:30 → 23:05/)).toBeInTheDocument();
  });

  it("expands a row on click to reveal detail", () => {
    render(<FlightsPanel data={DATA} />, { wrapper: Intl });
    expect(screen.queryByText(/seats left/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/VJ155/));
    expect(screen.getByText(/seats left/i)).toBeInTheDocument();
  });
});
