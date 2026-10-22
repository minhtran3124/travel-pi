import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";

import { useSubmitFeedback, type FeedbackRequest } from "./feedback";

const BASE = "/api/be";
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function wrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

/** msw handler that records every body and holds each request until
 * `release()` — which first waits for the handler to actually park. */
function deferredHandler(status = 201) {
  const bodies: FeedbackRequest[] = [];
  const releases: Array<() => void> = [];
  server.use(
    http.post(`${BASE}/agent/feedback`, async ({ request }) => {
      const body = (await request.json()) as FeedbackRequest;
      bodies.push(body);
      await new Promise<void>((resolve) => releases.push(resolve));
      return HttpResponse.json(
        {
          feedback_event_id: `ev-${bodies.length}`,
          assistant_message_id: body.assistant_message_id,
          effective_feedback: null,
          replayed: false,
        },
        { status },
      );
    }),
  );
  return {
    bodies,
    release: async () => {
      await waitFor(() => expect(releases.length).toBeGreaterThan(0));
      releases.splice(0).forEach((r) => r());
    },
  };
}

describe("useSubmitFeedback", () => {
  it("mints one client_event_id per submit and reuses it on retry", async () => {
    const { bodies, release } = deferredHandler();
    const { result } = renderHook(() => useSubmitFeedback(), {
      wrapper: wrapper(),
    });

    let first!: Promise<unknown>;
    act(() => {
      first = result.current.submit({
        assistant_message_id: "m1",
        action: "set_rating",
        rating: "helpful",
      });
    });
    await act(async () => {
      await release();
      await first;
    });
    expect(bodies).toHaveLength(1);
    expect(bodies[0].client_event_id).toMatch(UUID_RE);

    let second!: Promise<unknown>;
    act(() => {
      second = result.current.retry("m1");
    });
    await act(async () => {
      await release();
      await second;
    });
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toEqual(bodies[0]);
  });

  it("shares the pending request for the same message (double-click guard)", async () => {
    const { bodies, release } = deferredHandler();
    const { result } = renderHook(() => useSubmitFeedback(), {
      wrapper: wrapper(),
    });

    let a!: Promise<unknown>;
    let b!: Promise<unknown>;
    act(() => {
      a = result.current.submit({
        assistant_message_id: "m1",
        action: "set_rating",
        rating: "helpful",
      });
      b = result.current.submit({
        assistant_message_id: "m1",
        action: "set_rating",
        rating: "helpful",
      });
    });
    expect(b).toBe(a);
    await act(async () => {
      await release();
      await a;
    });
    expect(bodies).toHaveLength(1);
  });

  it("mints a new id for a deliberate change after the previous action settled", async () => {
    const { bodies, release } = deferredHandler();
    const { result } = renderHook(() => useSubmitFeedback(), {
      wrapper: wrapper(),
    });

    let first!: Promise<unknown>;
    act(() => {
      first = result.current.submit({
        assistant_message_id: "m1",
        action: "set_rating",
        rating: "helpful",
      });
    });
    await act(async () => {
      await release();
      await first;
    });
    let second!: Promise<unknown>;
    act(() => {
      second = result.current.submit({
        assistant_message_id: "m1",
        action: "set_rating",
        rating: "not_helpful",
      });
    });
    await act(async () => {
      await release();
      await second;
    });
    expect(bodies).toHaveLength(2);
    expect(bodies[1].client_event_id).not.toBe(bodies[0].client_event_id);
  });

  it("resolves retry to undefined when nothing was submitted for the message", async () => {
    const { result } = renderHook(() => useSubmitFeedback(), {
      wrapper: wrapper(),
    });
    await expect(result.current.retry("never")).resolves.toBeUndefined();
  });
});
