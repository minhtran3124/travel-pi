import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";

import {
  ClaimError,
  fetchClaim,
  fetchConversationMessages,
  type ConversationMessages,
} from "./agent";

const BASE = "/api/be";

describe("fetchConversationMessages", () => {
  it("resolves the ConversationMessages object shape", async () => {
    const body: ConversationMessages = {
      messages: [
        {
          id: "m1",
          conversation_id: "c1",
          role: "user",
          content: "hi",
          tool_calls: null,
          created_at: "2026-06-20T10:00:00Z",
        },
      ],
      interrupt_pending: true,
      interrupt_payload: { type: "book_flight", draft: "confirm?" },
    };

    server.use(
      http.get(`${BASE}/agent/conversations/:id/messages`, () =>
        HttpResponse.json(body),
      ),
    );

    const result = await fetchConversationMessages("c1", "anon-1");

    expect(result.messages).toHaveLength(1);
    expect(result.messages[0].content).toBe("hi");
    expect(result.interrupt_pending).toBe(true);
    expect(result.interrupt_payload).toEqual({
      type: "book_flight",
      draft: "confirm?",
    });
  });
});

describe("fetchClaim", () => {
  it.each([403, 500])(
    "throws a ClaimError carrying the %i status",
    async (status) => {
      server.use(
        http.post(`${BASE}/agent/conversations/claim`, () =>
          HttpResponse.json({ detail: "nope" }, { status }),
        ),
      );

      const err = await fetchClaim("anon-1").catch((e) => e);

      expect(err).toBeInstanceOf(ClaimError);
      expect((err as ClaimError).status).toBe(status);
      expect(typeof (err as ClaimError).status).toBe("number");
    },
  );
});
