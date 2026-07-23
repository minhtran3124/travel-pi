import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));

// jsdom has no layout engine — scrollIntoView is referenced by MessageList's effect.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

import { MessageList } from "./MessageList";
import type { ChatMessage } from "./useAgentStream";

const msgs = (content: string): ChatMessage[] => [
  { id: "u", role: "user", content: "hi" },
  { id: "a", role: "assistant", content },
];

describe("MessageList — partial render during streaming", () => {
  it("paints partial assistant text mid-stream", () => {
    render(<MessageList messages={msgs("Visit Tokyo")} isStreaming />);
    expect(screen.getByText(/Visit Tokyo/)).toBeTruthy();
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
