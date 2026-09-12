"use client";

import { useMutation } from "@tanstack/react-query";
import { useCallback, useRef } from "react";

import { client, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type FeedbackRequest = components["schemas"]["FeedbackRequest"];
export type FeedbackResponse = components["schemas"]["FeedbackResponse"];
export type EffectiveFeedback = components["schemas"]["EffectiveFeedback"];
export type FeedbackReasonCode = components["schemas"]["FeedbackReasonCode"];

/** One logical UI action; the hook mints its `client_event_id`. */
export type FeedbackAction = Omit<FeedbackRequest, "client_event_id">;

/** POST /agent/feedback — the body's `client_event_id` is the idempotency key
 * (no `Idempotency-Key` header; see specs/user-feedback-v1/DESIGN.md §5.1). */
export function submitFeedback(body: FeedbackRequest): Promise<FeedbackResponse> {
  return unwrap(client.POST("/agent/feedback", { body }));
}

/**
 * Mutation over POST /agent/feedback implementing DESIGN §7.2:
 *
 * - `submit(action)` mints ONE `client_event_id` per logical action and retains
 *   the full payload, so `retry(assistantMessageId)` replays the same id/body
 *   (the server answers 200 `replayed` instead of appending a second event).
 * - Per-message in-flight guard: while a request for a message is pending,
 *   `submit` / `retry` for that same message return the pending promise instead
 *   of minting a new event, so a double-click shares one action.
 * - A deliberate new action (e.g. a rating change after the previous one
 *   settled) goes through `submit` again and therefore gets a fresh id.
 *
 * No optimistic UI here — that is the component's job.
 */
export function useSubmitFeedback() {
  const inflight = useRef(new Map<string, Promise<FeedbackResponse>>());
  const lastRequest = useRef(new Map<string, FeedbackRequest>());
  const mutation = useMutation({ mutationFn: submitFeedback });
  const { mutateAsync } = mutation;

  const send = useCallback(
    (body: FeedbackRequest): Promise<FeedbackResponse> => {
      const key = body.assistant_message_id;
      const pending = inflight.current.get(key);
      if (pending) return pending;

      lastRequest.current.set(key, body);
      const request = mutateAsync(body).finally(() => {
        if (inflight.current.get(key) === request) inflight.current.delete(key);
      });
      inflight.current.set(key, request);
      return request;
    },
    [mutateAsync],
  );

  const submit = useCallback(
    (action: FeedbackAction) =>
      send({ client_event_id: crypto.randomUUID(), ...action }),
    [send],
  );

  /** Re-send the last action for a message with the same id/payload; resolves
   * to `undefined` when nothing was ever submitted for it. */
  const retry = useCallback(
    (assistantMessageId: string) => {
      const last = lastRequest.current.get(assistantMessageId);
      return last ? send(last) : Promise.resolve(undefined);
    },
    [send],
  );

  return { submit, retry, mutation };
}
