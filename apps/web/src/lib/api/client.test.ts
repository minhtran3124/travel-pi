import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";
import { client } from "./client";

describe("api client — identity middleware", () => {
  it("does not attach an X-User-Id header to requests", async () => {
    let captured: Headers | undefined;
    server.use(
      http.get("/api/be/agent/manifest", ({ request }) => {
        captured = request.headers;
        return HttpResponse.json({ subagents: [], tools: [] });
      }),
    );

    const { error } = await client.GET("/agent/manifest");

    expect(error).toBeUndefined();
    expect(captured).toBeDefined();
    // The anonymous ownership hint is gone — the backend scopes on the bearer
    // subject (#118), never on a client-supplied id.
    expect(captured?.has("x-user-id")).toBe(false);
    // Logged out in the test env, so no bearer either — public GET is unaffected.
    expect(captured?.has("authorization")).toBe(false);
  });
});
