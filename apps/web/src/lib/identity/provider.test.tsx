import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IdentityProvider } from "./provider";
import { useIdentity } from "./useUserId";

// --- Supabase client mock ----------------------------------------------------
// The provider derives identity from the Supabase session: an initial
// getSession() resolve, then live updates via onAuthStateChange. We drive both
// from the test.
let sessionUser: { id: string } | null = null;
let authCallback: ((event: string, session: unknown) => void) | null = null;
const unsubscribe = vi.fn();

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({
        data: { session: sessionUser ? { user: sessionUser } : null },
      }),
      onAuthStateChange: (cb: (event: string, session: unknown) => void) => {
        authCallback = cb;
        return { data: { subscription: { unsubscribe } } };
      },
    },
  }),
}));

function Probe() {
  const { userId, status } = useIdentity();
  return (
    <span data-testid="probe">
      {status}:{userId ?? "null"}
    </span>
  );
}

function probeText() {
  return screen.getByTestId("probe").textContent;
}

describe("IdentityProvider", () => {
  beforeEach(() => {
    sessionUser = null;
    authCallback = null;
    unsubscribe.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("resolves to signed-out when there is no session", async () => {
    render(
      <IdentityProvider>
        <Probe />
      </IdentityProvider>,
    );

    await waitFor(() => expect(probeText()).toBe("signed-out:null"));
  });

  it("resolves to signed-in with the session user id", async () => {
    sessionUser = { id: "user-123" };

    render(
      <IdentityProvider>
        <Probe />
      </IdentityProvider>,
    );

    await waitFor(() => expect(probeText()).toBe("signed-in:user-123"));
  });

  it("tracks live sign-in via onAuthStateChange", async () => {
    render(
      <IdentityProvider>
        <Probe />
      </IdentityProvider>,
    );

    await waitFor(() => expect(probeText()).toBe("signed-out:null"));

    act(() => {
      authCallback?.("SIGNED_IN", { user: { id: "user-456" } });
    });

    await waitFor(() => expect(probeText()).toBe("signed-in:user-456"));

    // …and back to signed-out on sign-out.
    act(() => {
      authCallback?.("SIGNED_OUT", null);
    });
    await waitFor(() => expect(probeText()).toBe("signed-out:null"));
  });

  it("unsubscribes from auth changes on unmount", async () => {
    const { unmount } = render(
      <IdentityProvider>
        <Probe />
      </IdentityProvider>,
    );

    await waitFor(() => expect(probeText()).toBe("signed-out:null"));
    unmount();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });
});
