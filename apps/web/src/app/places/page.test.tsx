import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

const savedPlacesState = { data: undefined, isLoading: true, isError: false };

vi.mock("@/lib/query/places", () => ({
  DuplicatePlaceError: class DuplicatePlaceError extends Error {},
  useSavedPlaces: () => savedPlacesState,
  usePlaceSearch: () => ({ data: undefined, isLoading: false, isError: false }),
  useCreateSavedPlace: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSavedPlace: () => ({ mutate: vi.fn(), isPending: false }),
  useSetFavorite: () => ({ mutate: vi.fn(), isPending: false }),
  useSetVisited: () => ({ mutate: vi.fn(), isPending: false }),
}));

import PlacesPage from "./page";

describe("PlacesPage — loading state", () => {
  it("renders the grid skeleton while isLoading", () => {
    render(<PlacesPage />);
    expect(screen.getByTestId("saved-places-grid-skeleton")).toBeTruthy();
  });

  it("renders no spinner (animate-spin) within the loading skeleton", () => {
    render(<PlacesPage />);
    const skeleton = screen.getByTestId("saved-places-grid-skeleton");
    expect(skeleton.querySelector(".animate-spin")).toBeNull();
    const status = screen.getByRole("status");
    expect(status.querySelector(".animate-spin")).toBeNull();
  });

  it("keeps the filter row live while isLoading", () => {
    render(<PlacesPage />);
    expect(screen.getByText("favorites")).toBeTruthy();
    expect(screen.getByText("visitedFilter")).toBeTruthy();
  });

  it("exposes an sr-only role=status live region while isLoading", () => {
    render(<PlacesPage />);
    const status = screen.getByRole("status");
    expect(status.className).toContain("sr-only");
    expect(status.textContent).toBe("loadingLabel");
  });
});

describe("PlacesPage — loaded state", () => {
  it("keeps the sr-only live region mounted (with empty text) once loaded", () => {
    savedPlacesState.data = { results: [] } as never;
    savedPlacesState.isLoading = false;
    try {
      render(<PlacesPage />);
      const status = screen.getByRole("status");
      expect(status.className).toContain("sr-only");
      expect(status.textContent).toBe("");
    } finally {
      savedPlacesState.data = undefined;
      savedPlacesState.isLoading = true;
    }
  });
});
