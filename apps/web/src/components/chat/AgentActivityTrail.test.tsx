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

  it("renders the HITL approval step with its localized label", () => {
    renderTrail({
      steps: [step({ id: "plan-approved:a1", tool: "plan_approved", subagent: "booking", status: "ok" })],
      isStreaming: true,
    });
    expect(screen.getByText(en.Chat.activity.approved)).toBeTruthy();
    expect(screen.queryByText("plan_approved")).toBeNull();
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

  it("streaming: collapses 11 consecutive same-family steps into one row with a count", () => {
    const steps = Array.from({ length: 11 }, (_, i) =>
      step({ id: `j${i}`, tool: "add_itinerary_item", status: "ok" }),
    );
    renderTrail({ steps, isStreaming: true });

    const rows = screen.getAllByText(en.Chat.activity.journal);
    expect(rows).toHaveLength(1);
    expect(screen.getByText("×11")).toBeTruthy();
  });

  it("streaming: does not merge the same family across a different family in between", () => {
    renderTrail({
      steps: [
        step({ id: "a", tool: "search_hotels", status: "ok" }),
        step({ id: "b", tool: "get_weather", status: "ok" }),
        step({ id: "c", tool: "book_hotel", status: "ok" }),
      ],
      isStreaming: true,
    });

    expect(screen.getAllByText(en.Chat.activity.hotels)).toHaveLength(2);
  });

  it("streaming: a group containing an error renders the family error copy and a retry control", () => {
    const onRetry = () => {};
    renderTrail({
      steps: [
        step({ id: "a", tool: "search_hotels", status: "ok" }),
        step({ id: "b", tool: "book_hotel", status: "error" }),
      ],
      isStreaming: true,
      onRetry,
    });

    expect(screen.getByText(en.Chat.activity.error.hotels)).toBeTruthy();
    expect(screen.getByRole("button", { name: en.Chat.activity.retry })).toBeTruthy();
  });

  it("streaming: clicking retry invokes onRetry", () => {
    let called = false;
    renderTrail({
      steps: [step({ id: "a", tool: "book_hotel", status: "error" })],
      isStreaming: true,
      onRetry: () => {
        called = true;
      },
    });

    fireEvent.click(screen.getByRole("button", { name: en.Chat.activity.retry }));
    expect(called).toBe(true);
  });

  it("streaming: hides the retry control when onRetry is not provided", () => {
    renderTrail({
      steps: [step({ id: "a", tool: "book_hotel", status: "error" })],
      isStreaming: true,
    });

    expect(screen.queryByRole("button")).toBeNull();
  });

  it("done: the collapsed summary uses the friendly 'sorted' copy", () => {
    renderTrail({
      steps: [step({ id: "a", tool: "search_hotels", status: "ok" })],
      isStreaming: false,
      elapsedMs: 1000,
    });

    expect(screen.getByRole("button").textContent).toContain("Sorted");
  });
});
