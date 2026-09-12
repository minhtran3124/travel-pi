import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";

import en from "../../../messages/en.json";
import vi from "../../../messages/vi.json";
import type { EffectiveFeedback, FeedbackRequest } from "@/lib/query/feedback";
import { server } from "@/test/msw";

import { MessageFeedback } from "./MessageFeedback";

const BASE = "/api/be";
const F = en.Chat.feedback;

function renderWith(ui: ReactElement, messages = en, locale = "en") {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale={locale} messages={messages}>
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}

/** The BE's folded state for a request (good enough for the UI contract). */
function effective(body: FeedbackRequest): EffectiveFeedback | null {
  if (body.action === "retract_rating") return null;
  return {
    rating: body.rating ?? "not_helpful",
    reason_code: body.reason_code ?? null,
    comment_present: Boolean(body.comment),
    rating_event_id: "ev-rating",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

/** msw handler answering the n-th call with `statuses[n]` (default 201). With
 * `hold`, every request parks until `release()`. Records every body. */
function feedbackHandler(statuses: number[] = [], hold = false) {
  const bodies: FeedbackRequest[] = [];
  const releases: Array<() => void> = [];
  server.use(
    http.post(`${BASE}/agent/feedback`, async ({ request }) => {
      const body = (await request.json()) as FeedbackRequest;
      bodies.push(body);
      if (hold) await new Promise<void>((resolve) => releases.push(resolve));
      const status = statuses[bodies.length - 1] ?? 201;
      if (status >= 400) {
        return HttpResponse.json(
          { error: "Error", message: "", status_code: status, path: "/agent/feedback" },
          { status },
        );
      }
      return HttpResponse.json(
        {
          feedback_event_id: `ev-${bodies.length}`,
          assistant_message_id: body.assistant_message_id,
          effective_feedback: effective(body),
          replayed: false,
        },
        { status },
      );
    }),
  );
  return {
    bodies,
    release: async () => {
      await waitFor(() => expect(releases.length).toBeGreaterThan(0));
      releases.splice(0).forEach((r) => r());
    },
  };
}

const helpful = () => screen.getByRole("button", { name: F.helpful });
const notHelpful = () => screen.getByRole("button", { name: F.notHelpful });

describe("MessageFeedback — rating flows", () => {
  it("saves a helpful rating: pressed + polite 'saved' status; pressing again retracts", async () => {
    const { bodies } = feedbackHandler();
    renderWith(<MessageFeedback assistantMessageId="m1" />);

    expect(helpful()).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(helpful());
    await screen.findByText(F.saved);
    expect(helpful()).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent(F.saved);
    expect(bodies[0]).toMatchObject({
      assistant_message_id: "m1",
      action: "set_rating",
      rating: "helpful",
      locale: "en",
    });

    fireEvent.click(helpful());
    await screen.findByText(F.removed);
    expect(helpful()).toHaveAttribute("aria-pressed", "false");
    expect(bodies[1].action).toBe("retract_rating");
    // A deliberate second action mints a fresh client event id.
    expect(bodies[1].client_event_id).not.toBe(bodies[0].client_event_id);
  });

  it("replaces helpful with not helpful and offers the 'Tell us more' affordance", async () => {
    const { bodies } = feedbackHandler();
    renderWith(<MessageFeedback assistantMessageId="m1" />);

    fireEvent.click(helpful());
    await screen.findByText(F.saved);
    expect(screen.queryByRole("button", { name: F.tellUsMore })).toBeNull();

    fireEvent.click(notHelpful());
    await waitFor(() =>
      expect(notHelpful()).toHaveAttribute("aria-pressed", "true"),
    );
    await screen.findByRole("button", { name: F.tellUsMore });
    expect(helpful()).toHaveAttribute("aria-pressed", "false");
    expect(bodies[1]).toMatchObject({ action: "set_rating", rating: "not_helpful" });
  });

  it("disables only this message's controls while its request is pending", async () => {
    const { release } = feedbackHandler([], true);
    renderWith(<MessageFeedback assistantMessageId="m1" />);

    fireEvent.click(helpful());
    await screen.findByText(F.saving);
    expect(helpful()).toBeDisabled();
    expect(notHelpful()).toBeDisabled();

    await release();
    await screen.findByText(F.saved);
    expect(helpful()).toBeEnabled();
    expect(notHelpful()).toBeEnabled();
  });

  it("rolls back on failure and retries with the SAME client event id", async () => {
    const { bodies } = feedbackHandler([500, 201]);
    renderWith(<MessageFeedback assistantMessageId="m1" />);

    fireEvent.click(helpful());
    await screen.findByText(F.error);
    expect(helpful()).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByRole("button", { name: F.retry }));
    await screen.findByText(F.saved);
    expect(helpful()).toHaveAttribute("aria-pressed", "true");
    expect(bodies).toHaveLength(2);
    expect(bodies[1].client_event_id).toBe(bodies[0].client_event_id);
    expect(bodies[1]).toEqual(bodies[0]);
  });

  it("hides the controls on 404 (message cannot be rated) without any toast", async () => {
    feedbackHandler([404]);
    renderWith(<MessageFeedback assistantMessageId="fallback" />);

    fireEvent.click(helpful());
    await waitFor(() => expect(screen.queryByRole("group")).toBeNull());
    expect(screen.queryByText(F.error)).toBeNull();
  });

  it("renders the reloaded history state pressed with no stale success status", () => {
    feedbackHandler();
    renderWith(
      <MessageFeedback
        assistantMessageId="m1"
        initial={{
          rating: "not_helpful",
          reason_code: "incomplete",
          comment_present: false,
          rating_event_id: "ev-old",
          updated_at: "2026-01-01T00:00:00Z",
        }}
      />,
    );
    expect(notHelpful()).toHaveAttribute("aria-pressed", "true");
    expect(helpful()).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("status")).toHaveTextContent("");
    // A detail already exists for this rating — nothing more to add.
    expect(screen.queryByRole("button", { name: F.tellUsMore })).toBeNull();
  });

  it("renders in Vietnamese", () => {
    renderWith(<MessageFeedback assistantMessageId="m1" />, vi, "vi");
    expect(
      screen.getByRole("button", { name: vi.Chat.feedback.helpful }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: vi.Chat.feedback.groupLabel }),
    ).toBeInTheDocument();
  });
});

describe("MessageFeedback — not-helpful detail dialog", () => {
  async function openDialog() {
    fireEvent.click(notHelpful());
    const trigger = await screen.findByRole("button", { name: F.tellUsMore });
    // A real activation focuses the trigger first — that is what `Modal`
    // records as the element to restore focus to on close.
    trigger.focus();
    fireEvent.click(trigger);
    return screen.getByRole("dialog", { name: F.dialogTitle });
  }

  it("opens an accessible dialog: title, reason radios in a group, labelled comment with a count", async () => {
    feedbackHandler();
    renderWith(<MessageFeedback assistantMessageId="m1" />);
    const dialog = await openDialog();

    expect(within(dialog).getByRole("group", { name: F.reasonLegend })).toBeInTheDocument();
    expect(within(dialog).getAllByRole("radio")).toHaveLength(5);
    expect(
      within(dialog).getByRole("radio", { name: F.reasons.unsafe }),
    ).toBeInTheDocument();
    const textarea = within(dialog).getByLabelText(F.commentLabel);
    expect(textarea).toHaveAttribute("maxlength", "500");
    expect(textarea).toHaveAccessibleDescription(
      `${F.commentHint} 500 characters left`,
    );
    fireEvent.change(textarea, { target: { value: "ab" } });
    expect(within(dialog).getByText("498 characters left")).toBeInTheDocument();
  });

  it("saves a reason + comment as a separate add_detail event and closes", async () => {
    const { bodies } = feedbackHandler();
    renderWith(<MessageFeedback assistantMessageId="m1" />);
    const dialog = await openDialog();

    // Nothing chosen yet → nothing to save.
    expect(within(dialog).getByRole("button", { name: F.save })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("radio", { name: F.reasons.incorrect }));
    fireEvent.change(within(dialog).getByLabelText(F.commentLabel), {
      target: { value: "  wrong dates  " },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: F.save }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(bodies[1]).toMatchObject({
      action: "add_detail",
      reason_code: "incorrect",
      comment: "wrong dates",
    });
    expect(bodies[1].client_event_id).not.toBe(bodies[0].client_event_id);
    expect(notHelpful()).toHaveAttribute("aria-pressed", "true");
    // The detail is immutable once saved — the affordance goes away.
    expect(screen.queryByRole("button", { name: F.tellUsMore })).toBeNull();
  });

  it("moves focus to the pressed Not-helpful button after a successful Save (the trigger unmounts)", async () => {
    feedbackHandler();
    renderWith(<MessageFeedback assistantMessageId="m1" />);
    const dialog = await openDialog();
    // The modal took focus on open (first control).
    expect(dialog.contains(document.activeElement)).toBe(true);

    fireEvent.click(within(dialog).getByRole("radio", { name: F.reasons.incorrect }));
    fireEvent.click(within(dialog).getByRole("button", { name: F.save }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    // The "Tell us more" trigger is gone, so the Modal's own restore has no
    // live target — focus must land on the pressed thumb, never on <body>.
    expect(screen.queryByRole("button", { name: F.tellUsMore })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(notHelpful()));
  });

  it("skip / Escape close the dialog without retracting the saved rating", async () => {
    const { bodies } = feedbackHandler();
    renderWith(<MessageFeedback assistantMessageId="m1" />);
    const dialog = await openDialog();
    expect(dialog.contains(document.activeElement)).toBe(true);

    fireEvent.click(within(dialog).getByRole("button", { name: F.skip }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(notHelpful()).toHaveAttribute("aria-pressed", "true");
    // Skip keeps the Modal's own restore: focus returns to the trigger.
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: F.tellUsMore }),
    );

    fireEvent.click(screen.getByRole("button", { name: F.tellUsMore }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(notHelpful()).toHaveAttribute("aria-pressed", "true");
    expect(bodies).toHaveLength(1);
  });

  it("shows the error in the dialog and retries the detail with the same client event id", async () => {
    const { bodies } = feedbackHandler([201, 500, 201]);
    renderWith(<MessageFeedback assistantMessageId="m1" />);
    const dialog = await openDialog();

    fireEvent.click(within(dialog).getByRole("radio", { name: F.reasons.other }));
    fireEvent.click(within(dialog).getByRole("button", { name: F.save }));
    await within(dialog).findByText(F.error);
    // The error is programmatically associated with the comment field while
    // it shows (DESIGN §8.4).
    expect(within(dialog).getByLabelText(F.commentLabel)).toHaveAccessibleDescription(
      `${F.commentHint} 500 characters left ${F.error}`,
    );

    fireEvent.click(within(dialog).getByRole("button", { name: F.retry }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(bodies).toHaveLength(3);
    expect(bodies[2]).toEqual(bodies[1]);
  });

  it("a detail failure after the user closed the dialog reports inline and never reopens it", async () => {
    const { bodies, release } = feedbackHandler([201, 500, 201], true);
    renderWith(<MessageFeedback assistantMessageId="m1" />);

    fireEvent.click(notHelpful());
    await release();
    await screen.findByText(F.saved);
    fireEvent.click(await screen.findByRole("button", { name: F.tellUsMore }));
    const dialog = screen.getByRole("dialog", { name: F.dialogTitle });
    fireEvent.click(within(dialog).getByRole("radio", { name: F.reasons.other }));
    fireEvent.click(within(dialog).getByRole("button", { name: F.save }));
    await within(dialog).findByText(F.saving);

    // Skip while the Save is still in flight: the request now belongs to the
    // inline status row.
    fireEvent.click(within(dialog).getByRole("button", { name: F.skip }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(F.saving);

    await release(); // → 500
    await screen.findByText(F.error);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(notHelpful()).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: F.retry }));
    await release(); // → 201
    await screen.findByText(F.saved);
    expect(screen.queryByRole("dialog")).toBeNull();
    // The detail now exists — the affordance is gone.
    expect(screen.queryByRole("button", { name: F.tellUsMore })).toBeNull();
    expect(bodies).toHaveLength(3);
    expect(bodies[2]).toEqual(bodies[1]);
  });
});
