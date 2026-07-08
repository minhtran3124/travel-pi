import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import type { AirQualityPanelData } from "@/lib/stream/panel";
import { AirQualityPanel } from "./AirQualityPanel";
import { PanelIntlProvider } from "./PanelIntlProvider";

// Panels read STATIC labels via `useTranslations`, so they must render inside a
// PanelIntlProvider (the streamed-language provider used in production).
const Intl = ({ children }: { children: ReactNode }) => (
  <PanelIntlProvider language="en">{children}</PanelIntlProvider>
);

const DATA: AirQualityPanelData = {
  location_name: "Hanoi",
  country: "Vietnam",
  timezone: "Asia/Bangkok",
  time: "2026-06-30T14:00",
  us_aqi: 118,
  category: "Unhealthy for Sensitive Groups",
  emoji: "😷",
  band: "usg",
  advice: "Sensitive groups should reduce prolonged outdoor exertion.",
  pollutants: [
    { label: "PM2.5", value: 42.3, unit: "μg/m³", desc: "Fine particles" },
    { label: "PM10", value: 70.1, unit: "μg/m³", desc: "Coarse particles" },
    { label: "Ozone", value: null, unit: "μg/m³", desc: "O₃" },
    { label: "NO₂", value: 10.7, unit: "μg/m³", desc: "Nitrogen dioxide" },
    { label: "SO₂", value: 2.1, unit: "μg/m³", desc: "Sulphur dioxide" },
    { label: "CO", value: 189.5, unit: "μg/m³", desc: "Carbon monoxide" },
  ],
  forecast: [
    { date: "2026-06-30", max_us_aqi: 120, category: "Unhealthy for Sensitive Groups", emoji: "😷", band: "usg" },
    { date: "2026-07-01", max_us_aqi: null, category: "Unknown", emoji: "❓", band: "unknown" },
  ],
  attribution: "Air quality data by Open-Meteo.com (CC BY 4.0)",
};

describe("AirQualityPanel", () => {
  it("renders the AQI dial, advice, location and scale ends", () => {
    render(<AirQualityPanel data={DATA} />, { wrapper: Intl });
    expect(screen.getByText("118")).toBeInTheDocument(); // dial value
    expect(screen.getByText("US AQI")).toBeInTheDocument();
    expect(
      screen.getByText("Sensitive groups should reduce prolonged outdoor exertion."),
    ).toBeInTheDocument();
    expect(screen.getByText(/📍 Hanoi, Vietnam/)).toBeInTheDocument();
    expect(screen.getByText("0 Good")).toBeInTheDocument();
    expect(screen.getByText("300+ Hazardous")).toBeInTheDocument();
  });

  it("renders all six pollutants, showing — for unavailable values", () => {
    render(<AirQualityPanel data={DATA} />, { wrapper: Intl });
    expect(screen.getByText("PM2.5")).toBeInTheDocument();
    expect(screen.getByText("42.3")).toBeInTheDocument();
    expect(screen.getByText("CO")).toBeInTheDocument();
    // ozone (pollutant) and the data-less forecast day both show a dash
    expect(screen.getAllByText("—")).toHaveLength(2);
  });

  it("tags the first forecast day TODAY and carries peak AQI", () => {
    render(<AirQualityPanel data={DATA} />, { wrapper: Intl });
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByText("2026-07-01")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument(); // today's peak AQI
  });
});
