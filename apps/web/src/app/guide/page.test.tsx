import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw";
import en from "../../../messages/en.json";
import GuidePage from "./[city]/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ city: "Da Nang" }),
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={queryClient}>
        <GuidePage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

const VISA_DISCLAIMER =
  "Guidance is general and may not match every nationality — always confirm with the destination's embassy before you travel.";

const VISA = {
  city: "Da Nang",
  country: "Vietnam",
  found: true,
  entry: {
    visa_free_days: 45,
    visa_on_arrival: true,
    e_visa: true,
    passport_validity_months: 6,
    summary:
      "Many nationalities get 45 days visa-free; others can apply for a 90-day e-visa online before arrival.",
  },
  disclaimer: VISA_DISCLAIMER,
};

const TIPS = {
  city: "Da Nang",
  country: "Vietnam",
  count: 1,
  summary: "1 tip found",
  tips: [
    {
      id: "t1",
      category: "transport",
      scope: "city",
      title: "Use Grab for short rides",
      content: "Ride-hailing apps are cheap and metered fairly.",
      is_essential: true,
    },
  ],
};

const CLIMATE = {
  location: {
    name: "Da Nang",
    country: "Vietnam",
    latitude: 16.05,
    longitude: 108.2,
  },
  based_on_years: [2022, 2023, 2024],
  months: [
    {
      month: 1,
      name: "January",
      avg_temp_max_c: 26,
      avg_temp_min_c: 20,
      avg_precip_mm: 60,
      rainy_days: 8,
      comfort: "mild, dry",
    },
  ],
  best_months: [1],
  summary: "Da Nang has a tropical monsoon climate.",
  attribution: "Weather data by Open-Meteo.com (CC BY 4.0)",
};

describe("GuidePage", () => {
  it("renders all three sections with the visa disclaimer verbatim", async () => {
    server.use(
      http.get("/api/be/visa", () => HttpResponse.json(VISA)),
      http.get("/api/be/tips", () => HttpResponse.json(TIPS)),
      http.get("/api/be/destinations/climate", () =>
        HttpResponse.json(CLIMATE),
      ),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(VISA_DISCLAIMER)).toBeInTheDocument();
    });
    expect(screen.getByText("Use Grab for short rides")).toBeInTheDocument();
    expect(
      screen.getByText("Da Nang has a tropical monsoon climate."),
    ).toBeInTheDocument();
  });

  it("keeps the other two sections rendered when one endpoint fails", async () => {
    server.use(
      http.get("/api/be/visa", () =>
        HttpResponse.json(
          { error: "InternalError", message: "boom" },
          { status: 500 },
        ),
      ),
      http.get("/api/be/tips", () => HttpResponse.json(TIPS)),
      http.get("/api/be/destinations/climate", () =>
        HttpResponse.json(CLIMATE),
      ),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Use Grab for short rides")).toBeInTheDocument();
    });
    expect(
      screen.getByText("Da Nang has a tropical monsoon climate."),
    ).toBeInTheDocument();
    expect(screen.getByText("Could not load visa guidance")).toBeInTheDocument();
    expect(screen.queryByText(VISA_DISCLAIMER)).not.toBeInTheDocument();
  });
});
