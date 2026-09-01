import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { PanelArtifact } from "@/lib/stream/panel";
import en from "../../../messages/en.json";
import { ResultCard } from "./ResultCard";

// ResultCard resolves its title in the `Panel` namespace (same as SidePanel) and
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
// FlightsPanel would show, but the compact card must NOT — it only summarizes.
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

describe("ResultCard", () => {
  it("renders a titled card for a registered kind and fires onOpen on click", () => {
    const onOpen = vi.fn();
    render(<ResultCard panel={flights} onOpen={onOpen} />, { wrapper: Intl });

    // Localized Panel.tabs.flights title + Chat.result.open affordance.
    expect(screen.getByText("Flights")).toBeInTheDocument();
    expect(screen.getByText("Open")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button"));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenCalledWith(flights);
  });

  it("derives a one-line item-count summary from a list-like payload", () => {
    render(<ResultCard panel={flights} onOpen={() => undefined} />, {
      wrapper: Intl,
    });
    // Panel.places.results plural for count=2 → "2 results".
    expect(screen.getByText("2 results")).toBeInTheDocument();
  });

  it("never mounts the heavy renderer (no renderer-specific detail leaks)", () => {
    render(<ResultCard panel={flights} onOpen={() => undefined} />, {
      wrapper: Intl,
    });
    // Title present, but the FlightsPanel-only flight number is absent — proving
    // the card summarizes rather than mounting PANEL_RENDERERS[kind].
    expect(screen.getByText("Flights")).toBeInTheDocument();
    expect(screen.queryByText(/VN-EXPRESS-777/)).toBeNull();
  });

  it("renders nothing for a kind with no registered renderer", () => {
    const { container } = render(
      <ResultCard
        panel={{ toolCallId: "u1", kind: "mystery", data: {} }}
        onOpen={() => undefined}
      />,
      { wrapper: Intl },
    );
    expect(container.firstChild).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
