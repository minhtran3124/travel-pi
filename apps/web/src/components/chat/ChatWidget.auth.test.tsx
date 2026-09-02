import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Translations are mocked to the identity function, so assertions match on the
// message KEY rather than its resolved copy (the existing widget-test pattern).
vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("next/navigation", () => ({ usePathname: () => "/trips/abc" }));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

// The signed-out branch is under test — force a confirmed signed-out session.
const identity = { userId: null as string | null, status: "signed-out" };
vi.mock("@/lib/identity/useUserId", () => ({
  useIdentity: () => identity,
}));

// The stream hook must not fire any request in the signed-out state. It is still
// called (unconditionally) by the widget, so stub it to an inert shape.
const useAgentStreamMock = vi.fn(() => ({ panels: [], panelLanguage: "en" }));
vi.mock("./useAgentStream", () => ({
  useAgentStream: () => useAgentStreamMock(),
}));

// If the composer ever rendered, this stub would be the only thing that could
// trigger a send — so its absence from the tree proves no request path exists.
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

describe("ChatWidget — signed out", () => {
  it("shows the sign-in prompt linking to /auth/login and never renders the chat panel", () => {
    setViewport(false);
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    render(<ChatWidget />);
    open();

    // The sign-in invitation is shown…
    const link = screen.getByText("signInPrompt").closest("a");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("/auth/login");

    // …and the streaming panel (the only surface that can send) is absent, so
    // no `/agent/*` request is ever made.
    expect(screen.queryByTestId("chat-panel")).toBeNull();
    expect(screen.queryByTestId("chat-docked")).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();

    vi.unstubAllGlobals();
  });

  it("shows the prompt in the compact sheet too", () => {
    setViewport(true);
    render(<ChatWidget />);
    open();

    expect(screen.getByTestId("chat-sheet")).toBeTruthy();
    expect(screen.getByText("signInPrompt")).toBeTruthy();
    expect(screen.queryByTestId("chat-panel")).toBeNull();
  });
});
