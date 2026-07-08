import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { PanelArtifact } from "@/lib/stream/panel";
import { PanelIntlProvider } from "./PanelIntlProvider";
import { SidePanel } from "./SidePanel";

// Stub the renderers so the tab/active logic is tested without the MapLibre
// bundle the real RoutePanel pulls in. PANEL_LABEL_KEYS holds the `Panel.tabs.*`
// keys SidePanel resolves via `useTranslations`.
vi.mock("./registry", () => ({
  PANEL_RENDERERS: {
    route: () => <div>route-body</div>,
    weather: () => <div>weather-body</div>,
  },
  PANEL_LABEL_KEYS: { route: "tabs.route", weather: "tabs.weather" },
}));

// SidePanel reads its labels via `useTranslations`, so it must render inside a
// PanelIntlProvider (the streamed-language provider used in production).
const Intl = ({ children }: { children: ReactNode }) => (
  <PanelIntlProvider language="en">{children}</PanelIntlProvider>
);

const route: PanelArtifact = { toolCallId: "r1", kind: "route", data: {} };
const weather: PanelArtifact = { toolCallId: "w1", kind: "weather", data: {} };

describe("SidePanel", () => {
  it("renders nothing when no panel has a registered renderer (forward-compat)", () => {
    const { container } = render(
      <SidePanel
        panels={[{ toolCallId: "t1", kind: "places", data: {} }]}
        onClose={() => undefined}
      />,
      { wrapper: Intl },
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing for an empty panel list", () => {
    const { container } = render(
      <SidePanel panels={[]} onClose={() => undefined} />,
      { wrapper: Intl },
    );
    expect(container.firstChild).toBeNull();
  });

  it("surfaces a newly-arrived panel even after another is shown", () => {
    const { rerender } = render(
      <SidePanel panels={[route]} onClose={() => undefined} />,
      { wrapper: Intl },
    );
    expect(screen.getByText("route-body")).toBeInTheDocument();

    // Weather streams in (newest) → it becomes the active body, not just a tab.
    rerender(<SidePanel panels={[route, weather]} onClose={() => undefined} />);
    expect(screen.getByText("weather-body")).toBeInTheDocument();
  });

  it("keeps a user-pinned tab until a newer panel arrives, then focuses it", () => {
    const { rerender } = render(
      <SidePanel panels={[route, weather]} onClose={() => undefined} />,
      { wrapper: Intl },
    );
    // User pins the Route tab.
    fireEvent.click(screen.getByRole("button", { name: "Route" }));
    expect(screen.getByText("route-body")).toBeInTheDocument();

    // A fresh weather panel (new toolCallId) drops the pin and surfaces itself.
    const weather2: PanelArtifact = { ...weather, toolCallId: "w2" };
    rerender(<SidePanel panels={[route, weather2]} onClose={() => undefined} />);
    expect(screen.getByText("weather-body")).toBeInTheDocument();
  });

  it("labels the tabs in the streamed panel language", () => {
    // English catalog → "Route" / "Weather" tab labels.
    const { unmount } = render(
      <PanelIntlProvider language="en">
        <SidePanel panels={[route, weather]} onClose={() => undefined} />
      </PanelIntlProvider>,
    );
    expect(screen.getByRole("button", { name: "Route" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Weather" })).toBeInTheDocument();
    unmount();

    // Vietnamese catalog → "Lộ trình" / "Thời tiết" (vi.json Panel.tabs.*).
    render(
      <PanelIntlProvider language="vi">
        <SidePanel panels={[route, weather]} onClose={() => undefined} />
      </PanelIntlProvider>,
    );
    expect(screen.getByRole("button", { name: "Lộ trình" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thời tiết" })).toBeInTheDocument();
  });
});
