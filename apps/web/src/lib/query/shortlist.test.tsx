import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { ShortlistTab } from "@/components/trips/shortlist/ShortlistTab";
import { server } from "@/test/msw";

import messages from "../../../messages/en.json";

const TRIP_ID = "trip-123";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale="en" timeZone="UTC" messages={messages}>
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      </NextIntlClientProvider>
    );
  };
}

function freshClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

describe("ShortlistTab — add 409", () => {
  it("surfaces a non-crashing notice when the place is already shortlisted", async () => {
    server.use(
      // Empty shortlist to start.
      http.get("*/trips/:id/places", () => HttpResponse.json([])),
      // One saved place to add from.
      http.get("*/places/saved", () =>
        HttpResponse.json({
          total: 1,
          limit: 20,
          offset: 0,
          results: [
            {
              id: "saved-1",
              name: "Secret rooftop bar",
              city: "Hanoi",
              favorite: false,
              visited: false,
              created_at: "2026-01-01T00:00:00Z",
              short_code: "SPL-ABC123",
            },
          ],
        }),
      ),
      // Adding the place 409s — already on the shortlist.
      http.post("*/trips/:id/places", () =>
        HttpResponse.json(
          {
            error: "ConflictError",
            message: "Already shortlisted",
            status_code: 409,
            path: `/trips/${TRIP_ID}/places`,
          },
          { status: 409 },
        ),
      ),
    );

    const queryClient = freshClient();
    render(<ShortlistTab tripId={TRIP_ID} />, {
      wrapper: wrapper(queryClient),
    });

    // Open the saved-places picker and add the place.
    fireEvent.click(screen.getByRole("button", { name: "Add from saved" }));
    const addBtn = await screen.findByRole("button", { name: "Add" });
    fireEvent.click(addBtn);

    // The 409 surfaces as a friendly status message — the component does not crash.
    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent(/already on this trip's shortlist/i);
  });
});

describe("ShortlistTab — remove by link_id", () => {
  it("issues the DELETE against the entry's link_id, not its place_id", async () => {
    const LINK_ID = "LINK-XYZ";
    const PLACE_ID = "place-uuid-999";
    let deletedUrl: string | null = null;

    server.use(
      http.get("*/places/saved", () =>
        HttpResponse.json({ total: 0, limit: 20, offset: 0, results: [] }),
      ),
      http.get("*/trips/:id/places", () =>
        HttpResponse.json([
          {
            link_id: LINK_ID,
            source: "catalog",
            place: {
              id: PLACE_ID,
              name: "Old Quarter",
              city: "Hanoi",
              country: "Vietnam",
              category: "attraction",
              description: "",
              address: "",
              rating: 4.5,
              review_count: 100,
              price_level: 2,
              image_url: "",
              tags: [],
              is_recommended: true,
              short_code: "PLC-OLDQTR",
            },
          },
        ]),
      ),
      http.delete("*/trips/:id/places/:linkId", ({ request }) => {
        deletedUrl = request.url;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const queryClient = freshClient();
    render(<ShortlistTab tripId={TRIP_ID} />, {
      wrapper: wrapper(queryClient),
    });

    const removeBtn = await screen.findByRole("button", {
      name: "Remove Old Quarter",
    });
    fireEvent.click(removeBtn);

    await waitFor(() => expect(deletedUrl).not.toBeNull());
    expect(deletedUrl).toContain(`/places/${LINK_ID}`);
    expect(deletedUrl).not.toContain(PLACE_ID);
  });
});
