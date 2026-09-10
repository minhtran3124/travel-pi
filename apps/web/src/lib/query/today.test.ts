import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";
import { useAirQuality, useDayPlan, useRoute, useWeather } from "./today";

const TRIP_ID = "33333333-3333-3333-3333-333333333333";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function freshClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

describe("useDayPlan", () => {
  it("calls GET /trips/{id}/day-plan with the date query param", async () => {
    const queryClient = freshClient();
    let capturedDate: string | null = null;
    let capturedTrip: string | undefined;

    server.use(
      http.get("*/trips/:tripId/day-plan", ({ request, params }) => {
        capturedDate = new URL(request.url).searchParams.get("date");
        capturedTrip = params.tripId as string;
        return HttpResponse.json({ date: "2026-09-09", items: [] });
      }),
    );

    const { result } = renderHook(() => useDayPlan(TRIP_ID, "2026-09-09"), {
      wrapper: wrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(capturedTrip).toBe(TRIP_ID);
    expect(capturedDate).toBe("2026-09-09");
  });

  it("is disabled without a trip id", () => {
    const queryClient = freshClient();
    const { result } = renderHook(() => useDayPlan("", "2026-09-09"), {
      wrapper: wrapper(queryClient),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled without a date", () => {
    const queryClient = freshClient();
    const { result } = renderHook(() => useDayPlan(TRIP_ID, ""), {
      wrapper: wrapper(queryClient),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useWeather", () => {
  it("calls GET /weather with the city query param", async () => {
    const queryClient = freshClient();
    let capturedCity: string | null = null;

    server.use(
      http.get("*/weather", ({ request }) => {
        capturedCity = new URL(request.url).searchParams.get("city");
        return HttpResponse.json({ city: "Da Nang" });
      }),
    );

    const { result } = renderHook(() => useWeather("Da Nang"), {
      wrapper: wrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(capturedCity).toBe("Da Nang");
  });

  it("is disabled without a city", () => {
    const queryClient = freshClient();
    const { result } = renderHook(() => useWeather(""), {
      wrapper: wrapper(queryClient),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useAirQuality", () => {
  it("calls GET /air-quality with the city query param", async () => {
    const queryClient = freshClient();
    let capturedCity: string | null = null;

    server.use(
      http.get("*/air-quality", ({ request }) => {
        capturedCity = new URL(request.url).searchParams.get("city");
        return HttpResponse.json({ city: "Da Nang" });
      }),
    );

    const { result } = renderHook(() => useAirQuality("Da Nang"), {
      wrapper: wrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(capturedCity).toBe("Da Nang");
  });

  it("is disabled without a city", () => {
    const queryClient = freshClient();
    const { result } = renderHook(() => useAirQuality(""), {
      wrapper: wrapper(queryClient),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useRoute", () => {
  it("calls GET /places/route with origin and destination query params", async () => {
    const queryClient = freshClient();
    let origin: string | null = null;
    let destination: string | null = null;

    server.use(
      http.get("*/places/route", ({ request }) => {
        const params = new URL(request.url).searchParams;
        origin = params.get("origin");
        destination = params.get("destination");
        return HttpResponse.json({});
      }),
    );

    const { result } = renderHook(() => useRoute("place-a", "place-b"), {
      wrapper: wrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(origin).toBe("place-a");
    expect(destination).toBe("place-b");
  });

  it("is disabled without a from place id", () => {
    const queryClient = freshClient();
    const { result } = renderHook(() => useRoute("", "place-b"), {
      wrapper: wrapper(queryClient),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled without a to place id", () => {
    const queryClient = freshClient();
    const { result } = renderHook(() => useRoute("place-a", ""), {
      wrapper: wrapper(queryClient),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });
});
