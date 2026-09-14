import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

// Mock the wave-2 children so this suite asserts turn *composition* (which
// children render, and in what order) without pulling their heavy deps
// (the panel registry, clipboard, i18n label tables).
vi.mock("./AgentActivityTrail", () => ({
  AgentActivityTrail: ({
    steps,
    isStreaming,
  }: {
    steps: unknown[];
    isStreaming: boolean;
  }) =>
    steps.length ? (
      <div data-testid="trail" data-streaming={String(isStreaming)}>
        trail
      </div>
    ) : null,
}));
vi.mock("./ResultChips", () => ({
  ResultChips: ({ panels }: { panels: { kind: string }[] }) => (
    <div data-testid="card">{panels.map((p) => p.kind).join(",")}</div>
  ),
}));
vi.mock("./MessageActions", () => ({
  MessageActions: ({ onRegenerate }: { onRegenerate?: () => void }) => (
    <div data-testid="actions" data-regen={String(Boolean(onRegenerate))}>
      actions
    </div>
  ),
}));
vi.mock("./MessageFeedback", () => ({
  MessageFeedback: ({
    assistantMessageId,
    initial,
  }: {
    assistantMessageId: string;
    initial?: { rating: string } | null;
  }) => (
    <div
      data-testid="feedback"
      data-id={assistantMessageId}
      data-rating={initial?.rating ?? ""}
    />
  ),
}));

// jsdom has no layout engine — scrollIntoView is referenced by MessageList's effect.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

import { MessageList } from "./MessageList";
import type { PanelArtifact } from "@/lib/stream/panel";
import type { ActivityStep, ChatMessage } from "./useAgentStream";

const msgs = (content: string): ChatMessage[] => [
  { id: "u", role: "user", content: "hi", activity: [], panels: [] },
  { id: "a", role: "assistant", content, activity: [], panels: [] },
];

const step: ActivityStep = {
  id: "s1",
  tool: "search_hotels",
  subagent: null,
  status: "ok",
};
const panel: PanelArtifact = { toolCallId: "p1", kind: "hotels", data: {} };

const FOLLOWING = Node.DOCUMENT_POSITION_FOLLOWING;
const before = (a: Element, b: Element) =>
  Boolean(a.compareDocumentPosition(b) & FOLLOWING);

describe("MessageList — partial render during streaming", () => {
  it("paints partial assistant text mid-stream", () => {
    render(<MessageList messages={msgs("Visit Tokyo")} isStreaming />);
    expect(screen.getByText(/Visit Tokyo/)).toBeTruthy();
  });

  it("shows a pulsing dot ahead of the text while streaming with content", () => {
    const { container, rerender } = render(
      <MessageList messages={msgs("Visit Tokyo")} isStreaming />,
    );
    expect(container.querySelector(".tp-trail-dot")).toBeTruthy();

    // Once the turn finishes, the dot goes away — it marks in-flight streaming only.
    rerender(<MessageList messages={msgs("Visit Tokyo")} isStreaming={false} />);
    expect(container.querySelector(".tp-trail-dot")).toBeNull();
  });

  it("grows the painted text as content accumulates", () => {
    const { rerender } = render(
      <MessageList messages={msgs("Visit")} isStreaming />,
    );
    expect(screen.getByText(/Visit/)).toBeTruthy();
    rerender(<MessageList messages={msgs("Visit Tokyo Tower")} isStreaming />);
    expect(screen.getByText(/Visit Tokyo Tower/)).toBeTruthy();
  });
});

describe("MessageList — turn composition", () => {
  it("renders trail, bubble, card and actions in that order for a completed turn", () => {
    const messages: ChatMessage[] = [
      { id: "u", role: "user", content: "hi", activity: [], panels: [] },
      {
        id: "a",
        role: "assistant",
        content: "Here you go",
        activity: [step],
        panels: [panel],
      },
    ];
    render(
      <MessageList
        messages={messages}
        isStreaming={false}
        onOpenPanel={() => {}}
        onRegenerate={() => {}}
      />,
    );

    const trail = screen.getByTestId("trail");
    const bubble = screen.getByText("Here you go");
    const card = screen.getByTestId("card");
    const actions = screen.getByTestId("actions");

    expect(before(trail, bubble)).toBe(true);
    expect(before(bubble, card)).toBe(true);
    expect(before(card, actions)).toBe(true);
    // Regenerate is offered on the last assistant message.
    expect(actions.getAttribute("data-regen")).toBe("true");
  });

  it("defers actions AND panel chips while the last assistant message is streaming", () => {
    const messages: ChatMessage[] = [
      { id: "u", role: "user", content: "hi", activity: [], panels: [] },
      {
        id: "a",
        role: "assistant",
        content: "partial",
        activity: [step],
        panels: [panel],
      },
    ];
    render(<MessageList messages={messages} isStreaming onRegenerate={() => {}} />);

    expect(screen.queryByTestId("actions")).toBeNull();
    expect(screen.queryByTestId("card")).toBeNull();
    expect(screen.getByTestId("trail").getAttribute("data-streaming")).toBe(
      "true",
    );
  });

  it("shows the trail in place of TypingDots when steps exist but no content yet", () => {
    const messages: ChatMessage[] = [
      { id: "u", role: "user", content: "hi", activity: [], panels: [] },
      { id: "a", role: "assistant", content: "", activity: [step], panels: [] },
    ];
    render(<MessageList messages={messages} isStreaming />);

    expect(screen.getByTestId("trail")).toBeTruthy();
    // TypingDots' aria-label resolves to the raw key under the mocked i18n.
    expect(screen.queryByLabelText("typingAria")).toBeNull();
  });

  it("keeps TypingDots when the streaming turn has neither steps nor content", () => {
    const messages: ChatMessage[] = [
      { id: "u", role: "user", content: "hi", activity: [], panels: [] },
      { id: "a", role: "assistant", content: "", activity: [], panels: [] },
    ];
    render(<MessageList messages={messages} isStreaming />);

    expect(screen.getByLabelText("typingAria")).toBeTruthy();
    expect(screen.queryByTestId("trail")).toBeNull();
  });
});

describe("MessageList — feedback eligibility (DESIGN §7.1)", () => {
  const user = (id: string): ChatMessage => ({
    id,
    role: "user",
    content: "hi",
    activity: [],
    panels: [],
  });
  const assistant = (id: string, serverMessageId?: string): ChatMessage => ({
    id,
    role: "assistant",
    content: "answer",
    activity: [],
    panels: [],
    serverMessageId,
  });

  it("renders feedback only under a completed assistant message with a server id", () => {
    render(
      <MessageList
        messages={[user("u"), assistant("a", "srv-a")]}
        isStreaming={false}
      />,
    );
    const feedback = screen.getAllByTestId("feedback");
    expect(feedback).toHaveLength(1);
    expect(feedback[0].getAttribute("data-id")).toBe("srv-a");
  });

  it("shows nothing without a server id (streaming, interrupted, stopped or failed turns)", () => {
    render(
      <MessageList messages={[user("u"), assistant("a")]} isStreaming={false} />,
    );
    expect(screen.queryByTestId("feedback")).toBeNull();
  });

  it("shows nothing on an empty completed turn even with a server id (empty states never show feedback)", () => {
    render(
      <MessageList
        messages={[user("u"), { ...assistant("a", "srv-a"), content: "  \n " }]}
        isStreaming={false}
      />,
    );
    expect(screen.queryByTestId("feedback")).toBeNull();
  });

  it("hides feedback on the streaming turn but keeps it on earlier completed turns", () => {
    render(
      <MessageList
        messages={[user("u1"), assistant("a1", "srv-1"), user("u2"), assistant("a2", "srv-2")]}
        isStreaming
      />,
    );
    const feedback = screen.getAllByTestId("feedback");
    expect(feedback).toHaveLength(1);
    expect(feedback[0].getAttribute("data-id")).toBe("srv-1");
  });

  it("passes the reloaded history state through", () => {
    const rated: ChatMessage = {
      ...assistant("a", "srv-a"),
      feedback: {
        rating: "helpful",
        reason_code: null,
        comment_present: false,
        rating_event_id: "ev",
        updated_at: "2026-01-01T00:00:00Z",
      },
    };
    render(<MessageList messages={[user("u"), rated]} isStreaming={false} />);
    expect(screen.getByTestId("feedback").getAttribute("data-rating")).toBe(
      "helpful",
    );
  });
});
