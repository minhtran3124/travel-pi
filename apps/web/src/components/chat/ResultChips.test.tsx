import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { PanelArtifact } from "@/lib/stream/panel";
import en from "../../../messages/en.json";
import { ResultChips } from "./ResultChips";

// ResultChips resolves its title in the `Panel` namespace (same as SidePanel) and
// `result.open` in `Chat`, so both slices are handed to the provider.
const Intl = ({ children }: { children: ReactNode }) => (
  <NextIntlClientProvider
    locale="en"
    messages={{ Panel: en.Panel, Chat: en.Chat }}
  >
    {children}
  </NextIntlClientProvider>
);

// A flights payload: renderer-specific detail (the flight number) that a full
// FlightsPanel would show, but the compact chip must NOT — it only summarizes.
const flights: PanelArtifact = {
  toolCallId: "f1",
  kind: "flights",
  data: {
    flights: [
      { id: "a", flight_number: "VN-EXPRESS-777" },
      { id: "b", flight_number: "VN-888" },
    ],
  },
};

const weather: PanelArtifact = { toolCallId: "w1", kind: "weather", data: {} };

// Two places panels, distinguished only by category — the multi-category-tabs
// case ResultChips must title distinctly rather than collapsing both to "Places".
const cafes: PanelArtifact = {
  toolCallId: "p1",
  kind: "places",
  data: {
    city: "Hanoi",
    category: "cafe",
    results_count: 2,
    places: [{ id: "c1" }, { id: "c2" }],
  },
};

const restaurants: PanelArtifact = {
  toolCallId: "p2",
  kind: "places",
  data: {
    city: "Hanoi",
    category: "restaurant",
    results_count: 3,
    places: [{ id: "r1" }, { id: "r2" }, { id: "r3" }],
  },
};

const placesNoCategory: PanelArtifact = {
  toolCallId: "p3",
  kind: "places",
  data: {
    city: "Hanoi",
    category: null,
    results_count: 1,
    places: [{ id: "n1" }],
  },
};

describe("ResultChips", () => {
  it("titles each places chip by its category, with matching count badges", () => {
    render(<ResultChips panels={[cafes, restaurants]} onOpen={() => undefined} />, {
      wrapper: Intl,
    });
    expect(screen.getByText("cafe")).toBeInTheDocument();
    expect(screen.getByText("restaurant")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("falls back to the 'Places' title when the panel has no category", () => {
    render(<ResultChips panels={[placesNoCategory]} onOpen={() => undefined} />, {
      wrapper: Intl,
    });
    expect(screen.getByText("Places")).toBeInTheDocument();
  });


  it("renders a titled chip for a registered kind and fires onOpen on click", () => {
    const onOpen = vi.fn();
    render(<ResultChips panels={[flights]} onOpen={onOpen} />, {
      wrapper: Intl,
    });

    // Localized Panel.tabs.flights title on the chip.
    expect(screen.getByText("Flights")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button"));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenCalledWith(flights);
  });

  it("renders every panel as one chip in a single row container", () => {
    render(<ResultChips panels={[flights, weather]} onOpen={() => undefined} />, {
      wrapper: Intl,
    });
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);
    // Both chips share one flex-wrap container (one row, not stacked cards).
    expect(buttons[0].parentElement).toBe(buttons[1].parentElement);
  });

  it("shows an item-count badge and a plural accessible label for list-like payloads", () => {
    render(<ResultChips panels={[flights]} onOpen={() => undefined} />, {
      wrapper: Intl,
    });
    // Visible compact badge "2"; the Panel.places.results plural lives in the
    // accessible name ("Flights — 2 results (Open)").
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Flights — 2 results/ }),
    ).toBeInTheDocument();
  });

  it("never mounts the heavy renderer (no renderer-specific detail leaks)", () => {
    render(<ResultChips panels={[flights]} onOpen={() => undefined} />, {
      wrapper: Intl,
    });
    // Title present, but the FlightsPanel-only flight number is absent — proving
    // the chip summarizes rather than mounting PANEL_RENDERERS[kind].
    expect(screen.getByText("Flights")).toBeInTheDocument();
    expect(screen.queryByText(/VN-EXPRESS-777/)).toBeNull();
  });

  it("renders nothing when no panel has a registered renderer", () => {
    const { container } = render(
      <ResultChips
        panels={[{ toolCallId: "u1", kind: "mystery", data: {} }]}
        onOpen={() => undefined}
      />,
      { wrapper: Intl },
    );
    expect(container.firstChild).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
