import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("next/navigation", () => ({ usePathname: () => "/trips/abc" }));
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

// A streaming hook with one panel present, so at `sm`+ the drawer would render.
// `mockPanels` is mutable so a test can simulate a new panel streaming in and
// rerender against the updated value (vi.hoisted so the vi.mock factory below,
// which is hoisted above this file's imports, can close over the same array).
const { mockPanels } = vi.hoisted(() => ({
  mockPanels: [{ toolCallId: "t1", kind: "route", data: {} }] as Array<{
    toolCallId: string;
    kind: string;
    data: unknown;
  }>,
}));
const stream = vi.hoisted(() => ({
  onTurnComplete: undefined as
    | ((turn: { currentFlow: string | null }) => void)
    | undefined,
}));
vi.mock("./useAgentStream", () => ({
  useAgentStream: (opts: {
    onTurnComplete?: (turn: { currentFlow: string | null }) => void;
  }) => {
    stream.onTurnComplete = opts.onTurnComplete;
    return { panels: mockPanels, panelLanguage: "en" };
  },
}));

const research = vi.hoisted(() => ({
  done: null as null | {
    run_id: string;
    trip_id: string;
    status: string;
    thread_turn: number;
    files: string[];
    proposal_ready: boolean;
  },
  check: vi.fn(),
}));
vi.mock("./useResearchWatch", () => ({
  useResearchWatch: () => ({
    done: research.done,
    check: research.check,
    dismiss: vi.fn(),
  }),
}));

// Light child stubs — the widget's layout is the unit under test, not the panel.
vi.mock("./ChatPanel", () => ({
  ChatPanel: ({
    onOpenPanel,
    notice,
  }: {
    onOpenPanel?: (panel: { toolCallId: string; kind: string; data: unknown }) => void;
    notice?: React.ReactNode;
  }) => (
    <section data-testid="chat-panel">
      panel
      {notice}
      <button
        type="button"
        aria-label="open-cafe-panel"
        onClick={() =>
          onOpenPanel?.({
            toolCallId: "p1",
            kind: "places",
            data: { category: "cafe" },
          })
        }
      />
    </section>
  ),
}));
vi.mock("./panel/SidePanel", () => ({
  SidePanel: ({ focus }: { focus?: { key: string; nonce: number } }) => (
    <div data-testid="side-panel" data-focus-key={focus?.key} data-focus-nonce={focus?.nonce}>
      drawer
    </div>
  ),
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
  mockPanels.length = 0;
  mockPanels.push({ toolCallId: "t1", kind: "route", data: {} });
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

  it("opening a places chip focuses the drawer tab by panel key", () => {
    setViewport(false);
    render(<ChatWidget />);
    open();

    fireEvent.click(screen.getByLabelText("open-cafe-panel"));

    const sidePanel = screen.getByTestId("side-panel");
    expect(sidePanel.dataset.focusKey).toBe("places:cafe");
    expect(sidePanel.dataset.focusNonce).toBe("1");
  });

  it("a freshly streamed panel clears a stale chip focus from before a Hide", () => {
    setViewport(false);
    const { rerender } = render(<ChatWidget />);
    open();

    fireEvent.click(screen.getByLabelText("open-cafe-panel"));
    expect(screen.getByTestId("side-panel").dataset.focusKey).toBe("places:cafe");

    // Simulate a Hide (mapHidden=true) unmounting the drawer, then a new turn
    // streaming in a fresh panel — mimicked here by mutating the panel list
    // and rerendering, which is what the real hook does on the next SSE tick.
    mockPanels.push({ toolCallId: "t2", kind: "weather", data: {} });
    rerender(<ChatWidget />);

    expect(screen.getByTestId("side-panel").dataset.focusKey).toBeUndefined();
  });

  it("the first chip click after a new panel streams in still focuses the drawer", () => {
    setViewport(false);
    const { rerender } = render(<ChatWidget />);
    open();

    fireEvent.click(screen.getByLabelText("open-cafe-panel"));
    expect(screen.getByTestId("side-panel").dataset.focusNonce).toBe("1");

    mockPanels.push({ toolCallId: "t2", kind: "weather", data: {} });
    rerender(<ChatWidget />);
    expect(screen.getByTestId("side-panel").dataset.focusKey).toBeUndefined();

    fireEvent.click(screen.getByLabelText("open-cafe-panel"));
    const sidePanel = screen.getByTestId("side-panel");
    expect(sidePanel.dataset.focusKey).toBe("places:cafe");
    expect(sidePanel.dataset.focusNonce).toBe("2");
  });
});

describe("ChatWidget — research completion", () => {
  afterEach(() => {
    research.done = null;
    research.check.mockClear();
  });

  it("follows research only after a turn the research specialist handled", () => {
    setViewport(false);
    render(<ChatWidget />);

    stream.onTurnComplete?.({ currentFlow: "planner" });
    expect(research.check).not.toHaveBeenCalled();

    stream.onTurnComplete?.({ currentFlow: "research" });
    expect(research.check).toHaveBeenCalledTimes(1);
  });

  it("shows the research-done card in the open panel once a run completes", () => {
    research.done = {
      run_id: "run-1",
      trip_id: "abc",
      status: "completed",
      thread_turn: 1,
      files: ["flights.md"],
      proposal_ready: true,
    };
    setViewport(false);
    render(<ChatWidget />);
    open();

    expect(screen.getByTestId("research-done-card")).toBeInTheDocument();
  });
});
