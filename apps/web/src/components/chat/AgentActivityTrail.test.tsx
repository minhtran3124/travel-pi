import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import en from "../../../messages/en.json";
import { AgentActivityTrail } from "./AgentActivityTrail";
import type { ActivityStep } from "./useAgentStream";

function renderTrail(props: Parameters<typeof AgentActivityTrail>[0]) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <AgentActivityTrail {...props} />
    </NextIntlClientProvider>,
  );
}

const step = (over: Partial<ActivityStep> = {}): ActivityStep => ({
  id: over.id ?? "s1",
  tool: over.tool ?? "search_hotels",
  subagent: over.subagent ?? null,
  status: over.status ?? "running",
});

describe("AgentActivityTrail", () => {
  it("renders nothing when there are no steps", () => {
    const { container } = renderTrail({ steps: [], isStreaming: true });
    expect(container).toBeEmptyDOMElement();
  });

  it("streaming: shows one localized family label per step", () => {
    renderTrail({
      steps: [
        step({ id: "a", tool: "search_hotels" }),
        step({ id: "b", tool: "get_weather", status: "ok" }),
      ],
      isStreaming: true,
    });

    expect(screen.getByText(en.Chat.activity.hotels)).toBeTruthy();
    expect(screen.getByText(en.Chat.activity.weather)).toBeTruthy();
    // No collapse button while streaming.
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("streaming: falls back to the generic working label for unknown tools", () => {
    renderTrail({
      steps: [step({ id: "z", tool: "mystery_tool" })],
      isStreaming: true,
    });
    expect(screen.getByText(en.Chat.activity.working)).toBeTruthy();
  });

  it("never renders the raw tool name in the DOM", () => {
    const { container } = renderTrail({
      steps: [step({ id: "a", tool: "search_hotels" })],
      isStreaming: true,
    });
    expect(container.textContent).not.toContain("search_hotels");
  });

  it("done: collapses to a summary line that expands the rows on click", () => {
    renderTrail({
      steps: [
        step({ id: "a", tool: "search_hotels", status: "ok" }),
        step({ id: "b", tool: "get_weather", status: "ok" }),
      ],
      isStreaming: false,
      elapsedMs: 3400,
    });

    const button = screen.getByRole("button");
    // Collapsed: summary shows the count and elapsed seconds, rows are hidden.
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(button.textContent).toContain("2");
    expect(button.textContent).toContain("3");
    expect(screen.queryByText(en.Chat.activity.hotels)).toBeNull();

    fireEvent.click(button);

    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText(en.Chat.activity.hotels)).toBeTruthy();
    expect(screen.getByText(en.Chat.activity.weather)).toBeTruthy();
  });
});
