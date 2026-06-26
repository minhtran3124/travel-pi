import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";
import { useCreateTrip, useTrips } from "./trips";

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("useTrips", () => {
  it("returns the parsed paginated results", async () => {
    server.use(
      http.get("/api/be/trips", () =>
        HttpResponse.json({
          total: 1,
          limit: 20,
          offset: 0,
          results: [
            {
              id: "trip-1",
              title: "Da Nang long weekend",
              travelers: 2,
              created_at: "2026-01-01T00:00:00Z",
            },
          ],
        }),
      ),
    );

    const { result } = renderHook(() => useTrips(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.results).toHaveLength(1);
    expect(result.current.data?.results[0]?.title).toBe("Da Nang long weekend");
  });
});

describe("useCreateTrip", () => {
  it("issues a POST carrying an Idempotency-Key header", async () => {
    let idempotencyKey: string | null = null;
    server.use(
      http.post("/api/be/trips", ({ request }) => {
        idempotencyKey = request.headers.get("Idempotency-Key");
        return HttpResponse.json(
          {
            id: "trip-2",
            title: "Kyoto autumn",
            travelers: 1,
            created_at: "2026-01-01T00:00:00Z",
          },
          { status: 201 },
        );
      }),
    );

    const { result } = renderHook(() => useCreateTrip(), {
      wrapper: makeWrapper(),
    });

    result.current.mutate({ title: "Kyoto autumn", travelers: 1 });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(idempotencyKey).not.toBeNull();
    expect(idempotencyKey).toMatch(/[0-9a-f-]{36}/i);
  });
});
