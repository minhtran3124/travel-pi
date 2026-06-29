import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { WeatherPanelData } from "@/lib/stream/panel";
import { WeatherPanel } from "./WeatherPanel";

const DATA: WeatherPanelData = {
  location_name: "Da Nang",
  country: "Vietnam",
  timezone: "Asia/Ho_Chi_Minh",
  current: {
    temperature_c: 28.4,
    apparent_temperature_c: 36.1,
    relative_humidity: 95,
    wind_speed_kmh: 5.2,
    description: "Thunderstorm",
    emoji: "⛈️",
    condition: "storm",
    time: "2026-06-30T00:00",
  },
  daily: [
    {
      date: "2026-06-30",
      temp_min_c: 28,
      temp_max_c: 34,
      precipitation_probability_max: 92,
      description: "Thunderstorm with heavy hail",
      emoji: "⛈️",
      condition: "storm",
    },
    {
      date: "2026-07-01",
      temp_min_c: 26,
      temp_max_c: 32,
      precipitation_probability_max: null,
      description: "Thunderstorm with slight hail",
      emoji: "⛈️",
      condition: "storm",
    },
  ],
  attribution: "Weather data by Open-Meteo.com (CC BY 4.0)",
};

describe("WeatherPanel", () => {
  it("renders the current-conditions hero with rounded temp, feels-like and stats", () => {
    render(<WeatherPanel data={DATA} />);
    expect(screen.getByText("28")).toBeInTheDocument();
    expect(screen.getByText("Thunderstorm")).toBeInTheDocument();
    expect(screen.getByText("Feels like 36°C")).toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("Asia/Ho_Chi_Minh")).toBeInTheDocument();
    // ISO "T" separator is replaced with a space for the updated timestamp
    expect(screen.getByText("2026-06-30 00:00")).toBeInTheDocument();
    expect(screen.getByText(/📍 Da Nang, Vietnam/)).toBeInTheDocument();
  });

  it("tags the first forecast day TODAY and shows the rest by date", () => {
    render(<WeatherPanel data={DATA} />);
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByText("2026-07-01")).toBeInTheDocument();
    // first day's max/min, rounded
    expect(screen.getByText("34°")).toBeInTheDocument();
    expect(screen.getByText("28°")).toBeInTheDocument();
  });

  it("renders a precipitation bar only when probability is present", () => {
    render(<WeatherPanel data={DATA} />);
    // day 1 has 92%; day 2 is null → exactly one precip readout
    expect(screen.getByText("💧 92%")).toBeInTheDocument();
    expect(screen.getAllByText(/💧 \d+%/)).toHaveLength(1);
  });
});
