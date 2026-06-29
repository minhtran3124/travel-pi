import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PanelArtifact } from "@/lib/stream/panel";
import { SidePanel } from "./SidePanel";

// Stub the renderers so the tab/active logic is tested without the MapLibre
// bundle the real RoutePanel pulls in.
vi.mock("./registry", () => ({
  PANEL_RENDERERS: {
    route: () => <div>route-body</div>,
    weather: () => <div>weather-body</div>,
  },
  PANEL_LABELS: { route: "Route", weather: "Weather" },
}));

const route: PanelArtifact = { toolCallId: "r1", kind: "route", data: {} };
const weather: PanelArtifact = { toolCallId: "w1", kind: "weather", data: {} };

describe("SidePanel", () => {
  it("renders nothing when no panel has a registered renderer (forward-compat)", () => {
    const { container } = render(
      <SidePanel
        panels={[{ toolCallId: "t1", kind: "places", data: {} }]}
        onClose={() => undefined}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing for an empty panel list", () => {
    const { container } = render(
      <SidePanel panels={[]} onClose={() => undefined} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("surfaces a newly-arrived panel even after another is shown", () => {
    const { rerender } = render(
      <SidePanel panels={[route]} onClose={() => undefined} />,
    );
    expect(screen.getByText("route-body")).toBeInTheDocument();

    // Weather streams in (newest) → it becomes the active body, not just a tab.
    rerender(<SidePanel panels={[route, weather]} onClose={() => undefined} />);
    expect(screen.getByText("weather-body")).toBeInTheDocument();
  });

  it("keeps a user-pinned tab until a newer panel arrives, then focuses it", () => {
    const { rerender } = render(
      <SidePanel panels={[route, weather]} onClose={() => undefined} />,
    );
    // User pins the Route tab.
    fireEvent.click(screen.getByRole("button", { name: "Route" }));
    expect(screen.getByText("route-body")).toBeInTheDocument();

    // A fresh weather panel (new toolCallId) drops the pin and surfaces itself.
    const weather2: PanelArtifact = { ...weather, toolCallId: "w2" };
    rerender(<SidePanel panels={[route, weather2]} onClose={() => undefined} />);
    expect(screen.getByText("weather-body")).toBeInTheDocument();
  });
});
