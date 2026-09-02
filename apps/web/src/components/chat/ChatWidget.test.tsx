import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("next/navigation", () => ({ usePathname: () => "/trips/abc" }));
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

// A streaming hook with one panel present, so at `sm`+ the drawer would render.
vi.mock("./useAgentStream", () => ({
  useAgentStream: () => ({
    panels: [{ toolCallId: "t1", kind: "route", data: {} }],
    panelLanguage: "en",
  }),
}));

// Light child stubs — the widget's layout is the unit under test, not the panel.
vi.mock("./ChatPanel", () => ({
  ChatPanel: () => <section data-testid="chat-panel">panel</section>,
}));
vi.mock("./panel/SidePanel", () => ({
  SidePanel: () => <div data-testid="side-panel">drawer</div>,
}));
vi.mock("./panel/PanelIntlProvider", () => ({
  PanelIntlProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("./ChatLauncher", () => ({
  ChatLauncher: ({ onToggle }: { onToggle: () => void }) => (
    <button type="button" aria-label="launcher" onClick={onToggle} />
  ),
}));

import { ChatWidget } from "./ChatWidget";

/** Drive the `sm` breakpoint: compact === below 640px. */
function setViewport(compact: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: compact,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

function open() {
  fireEvent.click(screen.getByLabelText("launcher"));
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ChatWidget — responsive shell", () => {
  it("below sm: renders a full-viewport sheet and never the drawer", () => {
    setViewport(true);
    render(<ChatWidget />);
    open();

    const sheet = screen.getByTestId("chat-sheet");
    expect(sheet.className).toContain("inset-0");
    expect(sheet.className).toContain("h-dvh");
    expect(screen.getByTestId("chat-panel")).toBeTruthy();

    // The drawer and the docked side-by-side row are absent from the tree.
    expect(screen.queryByTestId("side-panel")).toBeNull();
    expect(screen.queryByTestId("chat-docked")).toBeNull();
  });

  it("at sm+: renders the docked side-by-side layout with the drawer", () => {
    setViewport(false);
    render(<ChatWidget />);
    open();

    expect(screen.getByTestId("chat-docked")).toBeTruthy();
    expect(screen.getByTestId("side-panel")).toBeTruthy();
    expect(screen.getByTestId("chat-panel")).toBeTruthy();

    // No full-viewport sheet at desktop width.
    expect(screen.queryByTestId("chat-sheet")).toBeNull();
  });
});
