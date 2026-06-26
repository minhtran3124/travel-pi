import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "@/lib/api/client";

import { IdentityProvider } from "./provider";
import { useUserId } from "./useUserId";

const STORAGE_KEY = "travel.userId";

function Probe() {
  const id = useUserId();
  return <span data-testid="uid">{id ?? "null"}</span>;
}

describe("IdentityProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    apiClient.setUserId(null);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("generates and persists a UUID when none exists", async () => {
    render(
      <IdentityProvider>
        <Probe />
      </IdentityProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("uid").textContent).not.toBe("null");
    });

    const stored = localStorage.getItem(STORAGE_KEY);
    expect(stored).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );
    expect(screen.getByTestId("uid").textContent).toBe(stored);
  });

  it("reuses the same id across remounts", async () => {
    const { unmount } = render(
      <IdentityProvider>
        <Probe />
      </IdentityProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("uid").textContent).not.toBe("null");
    });
    const firstId = localStorage.getItem(STORAGE_KEY);
    expect(firstId).not.toBeNull();

    unmount();

    render(
      <IdentityProvider>
        <Probe />
      </IdentityProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("uid").textContent).toBe(firstId);
    });
    expect(localStorage.getItem(STORAGE_KEY)).toBe(firstId);
  });

  it("seeds the id from existing localStorage", async () => {
    const seeded = "11111111-2222-3333-4444-555555555555";
    localStorage.setItem(STORAGE_KEY, seeded);

    render(
      <IdentityProvider>
        <Probe />
      </IdentityProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("uid").textContent).toBe(seeded);
    });
    expect(localStorage.getItem(STORAGE_KEY)).toBe(seeded);
  });

  it("pushes the id to the api client via setUserId", async () => {
    const spy = vi.spyOn(apiClient, "setUserId");

    render(
      <IdentityProvider>
        <Probe />
      </IdentityProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("uid").textContent).not.toBe("null");
    });

    const id = localStorage.getItem(STORAGE_KEY);
    expect(spy).toHaveBeenCalledWith(id);
    expect(apiClient.getUserId()).toBe(id);
  });
});
