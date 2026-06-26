import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";
import { qk } from "@/lib/api/keys";
import {
  DuplicatePlaceError,
  useCreateSavedPlace,
  useSetFavorite,
  type SavedPlace,
  type SavedPlaceListResponse,
} from "./places";

function makePlace(overrides: Partial<SavedPlace> = {}): SavedPlace {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    name: "Secret rooftop bar",
    city: "Hanoi",
    favorite: false,
    visited: false,
    created_at: "2026-01-01T00:00:00Z",
    short_code: "SPL-ABC123",
    ...overrides,
  };
}

function makeList(place: SavedPlace): SavedPlaceListResponse {
  return { total: 1, limit: 20, offset: 0, results: [place] };
}

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

function freshClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

describe("useSetFavorite (optimistic)", () => {
  it("rolls back to the snapshot when the flag endpoint returns 500", async () => {
    const place = makePlace({ favorite: false });
    const queryClient = freshClient();
    queryClient.setQueryData(qk.savedPlaces(), makeList(place));

    server.use(
      http.post("*/places/saved/:id/favorite", async () => {
        // Hold the response so the optimistic write is observable before the
        // 500 triggers the rollback.
        await delay(50);
        return HttpResponse.json(
          {
            error: "ServerError",
            message: "boom",
            status_code: 500,
            path: "/places/saved/x/favorite",
          },
          { status: 500 },
        );
      }),
    );

    const { result } = renderHook(() => useSetFavorite(), {
      wrapper: wrapper(queryClient),
    });

    act(() => {
      result.current.mutate({ id: place.id, value: true });
    });

    // Optimistic write lands before the request settles.
    await waitFor(() => {
      const data = queryClient.getQueryData<SavedPlaceListResponse>(
        qk.savedPlaces(),
      );
      expect(data?.results[0].favorite).toBe(true);
    });

    // The 500 triggers a rollback to the original flag value.
    await waitFor(() => expect(result.current.isError).toBe(true));
    const rolledBack = queryClient.getQueryData<SavedPlaceListResponse>(
      qk.savedPlaces(),
    );
    expect(rolledBack?.results[0].favorite).toBe(false);
  });

  it("keeps the optimistic value on success", async () => {
    const place = makePlace({ favorite: false });
    const queryClient = freshClient();
    queryClient.setQueryData(qk.savedPlaces(), makeList(place));

    server.use(
      http.post("*/places/saved/:id/favorite", () =>
        HttpResponse.json(makePlace({ favorite: true }), { status: 200 }),
      ),
    );

    const { result } = renderHook(() => useSetFavorite(), {
      wrapper: wrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({ id: place.id, value: true });
    });

    const data = queryClient.getQueryData<SavedPlaceListResponse>(
      qk.savedPlaces(),
    );
    expect(data?.results[0].favorite).toBe(true);
  });
});

describe("useCreateSavedPlace", () => {
  it("surfaces a DuplicatePlaceError with the hint on 409", async () => {
    const queryClient = freshClient();

    server.use(
      http.post("*/places/saved", () =>
        HttpResponse.json(
          {
            error: "ConflictError",
            message: "Already saved",
            status_code: 409,
            path: "/places/saved",
            hint: "SPL-ABC123",
          },
          { status: 409 },
        ),
      ),
    );

    const { result } = renderHook(() => useCreateSavedPlace(), {
      wrapper: wrapper(queryClient),
    });

    await expect(
      result.current.mutateAsync({
        name: "Secret rooftop bar",
        favorite: false,
        visited: false,
      }),
    ).rejects.toMatchObject({ hint: "SPL-ABC123" });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(DuplicatePlaceError);
  });
});
