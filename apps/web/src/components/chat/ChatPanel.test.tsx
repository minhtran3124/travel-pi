import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { UseAgentStream } from "./useAgentStream";

// Translations resolve to their key, so band assertions read cleanly.
vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

// Light child stubs — ChatPanel's band arbitration is the unit under test.
vi.mock("./ChatHeader", () => ({
  ChatHeader: ({
    onClose,
    isCompact,
  }: {
    onClose: () => void;
    isCompact?: boolean;
  }) => (
    <div data-testid="header" data-compact={String(!!isCompact)}>
      <button type="button" data-testid="header-close" onClick={onClose} />
    </div>
  ),
}));
vi.mock("./ChatEmptyState", () => ({
  ChatEmptyState: () => <div data-testid="empty" />,
}));
vi.mock("./MessageList", () => ({
  MessageList: ({
    onOpenPanel,
    onRegenerate,
  }: {
    onOpenPanel?: (p: unknown) => void;
    onRegenerate?: () => void;
  }) => (
    <div data-testid="message-list">
      <button
        type="button"
        data-testid="open-panel"
        onClick={() =>
          onOpenPanel?.({ toolCallId: "t1", kind: "route", data: {} })
        }
      />
      <button type="button" data-testid="regen" onClick={() => onRegenerate?.()} />
    </div>
  ),
}));
vi.mock("./ChatComposer", () => ({
  ChatComposer: ({ suggestions }: { suggestions?: React.ReactNode }) => (
    <div data-testid="composer">
      {suggestions ? <div data-testid="composer-rail">{suggestions}</div> : null}
    </div>
  ),
}));
vi.mock("./ChatSuggestions", () => ({
  ChatSuggestions: () => <div data-testid="suggestions-chips" />,
}));
vi.mock("./InterruptPrompt", () => ({
  InterruptPrompt: () => <div data-testid="interrupt" />,
}));
vi.mock("./panel/SidePanel", () => ({
  SidePanel: () => <section data-testid="side-panel-sheet" />,
}));
vi.mock("./panel/PanelIntlProvider", () => ({
  PanelIntlProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));
vi.mock("@/components/ui/ConfirmDialog", () => ({
  ConfirmDialog: () => null,
}));

import { ChatPanel } from "./ChatPanel";

function makeStream(overrides: Partial<UseAgentStream> = {}): UseAgentStream {
  return {
    messages: [
      { id: "u1", role: "user", content: "hi", activity: [], panels: [] },
      { id: "a1", role: "assistant", content: "hello", activity: [], panels: [] },
    ],
    send: vi.fn(),
    isStreaming: false,
    error: null,
    interrupt: null,
    resume: vi.fn(),
    canRetry: false,
    retry: vi.fn(),
    newConversation: vi.fn(),
    suggestions: ["addDay"],
    panels: [],
    panelLanguage: "en",
    ...overrides,
  } as UseAgentStream;
}

afterEach(() => {
  document.body.classList.remove("overflow-hidden");
  vi.clearAllMocks();
});

describe("ChatPanel — bands", () => {
  it("drops the standalone show/hide panel band", () => {
    render(
      <ChatPanel
        stream={makeStream({ panels: [{ toolCallId: "t1", kind: "route", data: {} }] })}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByText("Show panel")).toBeNull();
    expect(screen.queryByText("Hide panel")).toBeNull();
  });

  it("shows the composer with the chip rail when idle with suggestions", () => {
    render(<ChatPanel stream={makeStream()} onClose={vi.fn()} />);
    expect(screen.getByTestId("composer")).toBeTruthy();
    expect(screen.getByTestId("composer-rail")).toBeTruthy();
    expect(screen.getByTestId("suggestions-chips")).toBeTruthy();
  });

  it("suppresses the chip rail while streaming (one band only)", () => {
    render(
      <ChatPanel stream={makeStream({ isStreaming: true })} onClose={vi.fn()} />,
    );
    expect(screen.getByTestId("composer")).toBeTruthy();
    expect(screen.queryByTestId("composer-rail")).toBeNull();
  });

  it("an interrupt replaces the composer and its rail", () => {
    render(
      <ChatPanel
        stream={makeStream({ interrupt: { payload: { draft: "d" } } as never })}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId("interrupt")).toBeTruthy();
    expect(screen.queryByTestId("composer")).toBeNull();
    expect(screen.queryByTestId("composer-rail")).toBeNull();
  });

  it("a retryable error replaces the composer with the retry band", () => {
    render(<ChatPanel stream={makeStream({ canRetry: true })} onClose={vi.fn()} />);
    expect(screen.getByText("retry")).toBeTruthy();
    expect(screen.queryByTestId("composer")).toBeNull();
  });
});

describe("ChatPanel — compact sheet a11y", () => {
  it("marks the dialog aria-modal in compact mode only", () => {
    const { rerender } = render(
      <ChatPanel stream={makeStream()} onClose={vi.fn()} isCompact />,
    );
    expect(screen.getByRole("dialog").getAttribute("aria-modal")).toBe("true");

    rerender(<ChatPanel stream={makeStream()} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog").getAttribute("aria-modal")).toBeNull();
  });

  it("Escape closes the compact sheet", () => {
    const onClose = vi.fn();
    render(<ChatPanel stream={makeStream()} onClose={onClose} isCompact />);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("locks body scroll while the compact sheet is open", () => {
    const { unmount } = render(
      <ChatPanel stream={makeStream()} onClose={vi.fn()} isCompact />,
    );
    expect(document.body.classList.contains("overflow-hidden")).toBe(true);
    unmount();
    expect(document.body.classList.contains("overflow-hidden")).toBe(false);
  });

  it("opens a result panel in an in-sheet bottom sheet in compact mode", () => {
    render(<ChatPanel stream={makeStream()} onClose={vi.fn()} isCompact />);
    expect(screen.queryByTestId("side-panel-sheet")).toBeNull();
    fireEvent.click(screen.getByTestId("open-panel"));
    expect(screen.getByTestId("side-panel-sheet")).toBeTruthy();
  });

  it("delegates result-panel opening to onOpenPanel on desktop", () => {
    const onOpenPanel = vi.fn();
    render(
      <ChatPanel stream={makeStream()} onClose={vi.fn()} onOpenPanel={onOpenPanel} />,
    );
    fireEvent.click(screen.getByTestId("open-panel"));
    expect(onOpenPanel).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("side-panel-sheet")).toBeNull();
  });
});

describe("ChatPanel — motion", () => {
  it("pairs each new keyframe with a reduced-motion no-op", () => {
    const css = readFileSync(resolve("src/app/globals.css"), "utf8");
    expect(css).toContain("@keyframes tp-trail-dot");
    expect(css).toContain("@keyframes tp-card-in");

    const reduced = css.slice(css.indexOf("prefers-reduced-motion"));
    expect(reduced).toMatch(/\.tp-trail-dot\s*\{\s*animation:\s*none/);
    expect(reduced).toMatch(/\.tp-card-in\s*\{\s*animation:\s*none/);
  });
});
