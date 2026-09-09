import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import type { AirQualityResponse } from "@/lib/query/today";

import en from "../../../../messages/en.json";
import { aqiBand, TodayAirQualityCard } from "./TodayAirQualityCard";

function makeAir(overrides: Partial<AirQualityResponse> = {}): AirQualityResponse {
  return {
    location: { name: "Da Nang", latitude: 16.07, longitude: 108.23 },
    time: "2026-06-16T14:00",
    us_aqi: 35,
    category: "Good",
    pm2_5: 8.3,
    ...overrides,
  } as AirQualityResponse;
}

function renderCard(data: AirQualityResponse | undefined) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <TodayAirQualityCard data={data} />
    </NextIntlClientProvider>,
  );
}

describe("aqiBand", () => {
  // Every band boundary, both edges — a single mid-band value proves nothing.
  const cases: [number, string][] = [
    [0, "good"],
    [50, "good"],
    [51, "moderate"],
    [100, "moderate"],
    [101, "unhealthySensitive"],
    [150, "unhealthySensitive"],
    [151, "unhealthy"],
    [200, "unhealthy"],
    [201, "veryUnhealthy"],
    [300, "veryUnhealthy"],
    [301, "hazardous"],
  ];

  it.each(cases)("maps %i to %s", (aqi, band) => {
    expect(aqiBand(aqi)).toBe(band);
  });
});

describe("TodayAirQualityCard", () => {
  // Each boundary renders the number and its exact localized band label.
  // getByText is exact by default, so "Unhealthy" never matches
  // "Unhealthy for sensitive groups" or "Very unhealthy".
  const rendered: [number, string][] = [
    [0, "Good"],
    [50, "Good"],
    [51, "Moderate"],
    [100, "Moderate"],
    [101, "Unhealthy for sensitive groups"],
    [150, "Unhealthy for sensitive groups"],
    [151, "Unhealthy"],
    [200, "Unhealthy"],
    [201, "Very unhealthy"],
    [300, "Very unhealthy"],
    [301, "Hazardous"],
  ];

  it.each(rendered)(
    "renders %i with the band label %s",
    (aqi, label) => {
      renderCard(makeAir({ us_aqi: aqi }));
      expect(screen.getByText(String(aqi))).toBeInTheDocument();
      expect(screen.getByText(label)).toBeInTheDocument();
    },
  );

  it("falls back to the API category and hides the number when us_aqi is null", () => {
    renderCard(makeAir({ us_aqi: null, category: "Moderate", pm2_5: null }));
    // The verbatim API category is shown.
    expect(screen.getByText("Moderate")).toBeInTheDocument();
    // No numeric reading and no US-AQI label.
    expect(screen.queryByText(en.Today.air.aqi)).not.toBeInTheDocument();
  });

  it("shows PM2.5 only when it is non-null", () => {
    const { unmount } = renderCard(makeAir({ us_aqi: 35, pm2_5: 8.3 }));
    expect(screen.getByText("8.3")).toBeInTheDocument();
    unmount();

    renderCard(makeAir({ us_aqi: 35, pm2_5: null }));
    expect(screen.queryByText(en.Today.air.pm25, { exact: false })).not.toBeInTheDocument();
  });

  it("renders nothing when the data prop is undefined", () => {
    const { container } = renderCard(undefined);
    expect(container).toBeEmptyDOMElement();
  });
});
