import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import en from "../../../../messages/en.json";
import type { WeatherResponse } from "@/lib/query/today";
import { TodayWeatherCard } from "./TodayWeatherCard";

type CurrentWeather = WeatherResponse["current"];

function renderCard(
  current: CurrentWeather | undefined,
  flags: { isPending?: boolean; isError?: boolean } = {},
) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <TodayWeatherCard current={current} {...flags} />
    </NextIntlClientProvider>,
  );
}

function makeCurrent(overrides: Partial<CurrentWeather> = {}): CurrentWeather {
  return {
    time: "2026-09-09T08:00",
    temperature_c: 27.4,
    apparent_temperature_c: 30.1,
    relative_humidity: 78,
    wind_speed_kmh: 12.6,
    weather_code: 61,
    description: "Slight rain from the API",
    ...overrides,
  };
}

const w = en.Today.weather;

describe("TodayWeatherCard", () => {
  it("renders the localized WMO condition for a known code", () => {
    renderCard(makeCurrent({ weather_code: 61 }));

    // 61 -> "Slight rain" from the map, not the API's own description text.
    expect(screen.getByText(w.wmo["61"])).toBeTruthy();
    expect(screen.queryByText("Slight rain from the API")).toBeNull();
  });

  it("falls back to the API description when the code is not in the map", () => {
    renderCard(
      makeCurrent({ weather_code: 100, description: "Unmapped API summary" }),
    );

    // 100 has no entry in Today.weather.wmo -> the response's own text is shown.
    expect(screen.getByText("Unmapped API summary")).toBeTruthy();
  });

  it("renders temperature, feels-like, humidity and wind from the response fields", () => {
    renderCard(makeCurrent());

    expect(screen.getByText(w.temperature)).toBeTruthy();
    expect(screen.getByText("27°C")).toBeTruthy();
    expect(screen.getByText(w.feelsLike)).toBeTruthy();
    expect(screen.getByText("30°C")).toBeTruthy();
    expect(screen.getByText(w.humidity)).toBeTruthy();
    expect(screen.getByText("78%")).toBeTruthy();
    expect(screen.getByText(w.wind)).toBeTruthy();
    expect(screen.getByText("13 km/h")).toBeTruthy();
  });

  it("renders nothing when no current reading is supplied", () => {
    const { container } = renderCard(undefined);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a spinner while the weather query is pending", () => {
    // No `current` yet, but the query is in flight — a spinner, not blank.
    renderCard(undefined, { isPending: true });
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(en.Common.loading)).toBeTruthy();
  });

  it("shows an error state when the weather query fails", () => {
    // Failed query: isError true, no data. It must not render blank.
    renderCard(undefined, { isError: true });
    expect(
      screen.getByText(en.Errors.somethingWentWrongTitle),
    ).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
