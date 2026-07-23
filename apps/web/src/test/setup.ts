import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach } from "vitest";
import { server } from "./msw";

// Supabase's browser client (src/lib/supabase/client.ts) throws at construction
// when these are unset, which crashes any test that mounts a component calling
// createClient() (e.g. useAgentStream's claim/hydrate effect). The values are
// never dialed — getSession() reads local storage and returns null with no
// network — so dummy placeholders are enough to keep the client constructible.
process.env.NEXT_PUBLIC_SUPABASE_URL ??= "https://test.supabase.co";
process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??= "test-publishable-key";

// The API client uses a relative baseUrl ("/api/be") that the browser resolves
// against the page origin. Two things break that in the Node test env, both
// handled here:
//
// 1. openapi-fetch builds `new Request("/api/be/...")` before calling fetch, and
//    undici's Request rejects relative URLs. We subclass the global Request to
//    absolutize relative string inputs against the jsdom origin.
// 2. openapi-fetch captures `globalThis.fetch` at createClient() time (module
//    import). MSW must therefore patch fetch BEFORE the client module is
//    imported, so `server.listen()` runs at top level here (setup files finish
//    before test modules are imported), not inside beforeAll.
const RealRequest = globalThis.Request;
class RelativeAwareRequest extends RealRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    if (typeof input === "string" && input.startsWith("/")) {
      super(new URL(input, location.href).toString(), init);
      return;
    }
    if (input instanceof URL && input.href.startsWith("/")) {
      super(new URL(input.href, location.href).toString(), init);
      return;
    }
    super(input, init);
  }
}
globalThis.Request = RelativeAwareRequest as typeof Request;

server.listen({ onUnhandledRequest: "error" });
afterEach(() => server.resetHandlers());
afterAll(() => {
  globalThis.Request = RealRequest;
  server.close();
});
