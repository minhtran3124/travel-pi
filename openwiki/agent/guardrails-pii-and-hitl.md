---
type: concept
title: "Guardrails: PII, memory poisoning and human-in-the-loop"
description: The safety layers around the travel agent — credit-card redaction before any model call, the booking plan-approval interrupt and resume path, confirm/ownership protections on destructive tools, the trip guard, and the deterministic write/read guard plus prompt wrapping that contain long-term memory poisoning.
tags: [guardrails, pii, hitl, interrupt, memory-poisoning, booking, safety, langgraph]
sources:
  - id: openwiki-source-653637f2675661d4499c6d01
    resource: repo://apps/api/app/agents/constants.py
  - id: openwiki-source-a5f185a5567d6ef95e596338
    resource: repo://apps/api/app/agents/context.py
  - id: openwiki-source-eb5166092c9ccf2f147f108a
    resource: repo://apps/api/app/agents/guardrails.py
  - id: openwiki-source-aab651981316f0a542a5e4dd
    resource: repo://apps/api/app/agents/state.py
  - id: openwiki-source-0e29236b52482e5a3cdf5f04
    resource: repo://apps/api/app/agents/subagents/_base.py
  - id: openwiki-source-6bf7699cddc35845704fa65b
    resource: repo://apps/api/app/agents/supervisor.py
  - id: openwiki-source-185823a428ccf3122dfd78c4
    resource: repo://apps/api/app/memory/guard.py
  - id: openwiki-source-40fb538510ad8b559a8e282e
    resource: repo://apps/api/app/routers/agent.py
  - id: openwiki-source-6363628a1f671621e4823cd8
    resource: repo://apps/api/app/tools/booking_tools.py
  - id: openwiki-source-fbd9573b3a515ae531651926
    resource: repo://apps/api/app/tools/hotel_tools.py
  - id: openwiki-source-97b1fd4b365c73190c64c4c1
    resource: repo://apps/api/app/tools/registry.py
  - id: openwiki-source-49bdf06b3dac7c681ce9efd5
    resource: repo://apps/api/tests/agents/test_load_context_memory_guard.py
  - id: openwiki-source-d18bdec23d21d9be3faf72ca
    resource: repo://apps/api/tests/agents/test_pii_redaction.py
  - id: openwiki-source-827a5601a0a66b0a5f322177
    resource: repo://apps/api/tests/agents/test_trip_guard.py
  - id: openwiki-source-332dfb1424208ef02de55e80
    resource: repo://apps/api/tests/memory/test_guard.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
verified:
  - by: openwiki/0.5.2
    at: 2026-09-21T09:19:54.601Z
---

# Guardrails: PII, memory poisoning and human-in-the-loop

The agent has no single "safety module". Instead, several small deterministic layers sit at the boundaries where untrusted text enters the system (the traveller's message, tool output, stored memory) and where irreversible actions leave it (bookings, cancellations). This page describes each layer, where it runs in the graph described in [Agent graph and supervisor routing](graph-and-supervisor.md), and what it deliberately does not do.

## 1. PII redaction at the graph entry

`pii_guardrail_node` (`apps/api/app/agents/guardrails.py`) is the first node of the graph. It rewrites the **latest `HumanMessage`** in place: the returned message keeps the original `id`, so the `add_messages` reducer *replaces* rather than appends, and the raw text never reaches the checkpointer. If the message has no id, is not plain text, or contains no PII, the node returns an empty update.

What it redacts is narrow on purpose: **credit-card numbers only**, masked to `****-****-****-<last4>`. Names, phones and emails are left intact because the memory extractor reads names and the booking flow needs the raw phone and email. Detection is a broad digit-run regex followed by a **Luhn window search** over common card lengths, so a card glued to an expiry or CVV is still caught, while an incidental digit run that fails Luhn is spared. `tests/agents/test_pii_redaction.py` pins each of these behaviors (email untouched, card with expiry masked, non-Luhn numbers untouched, in-place replacement of the newest human message).

The same `redact_pii` function is also applied by the agent router **before the user turn is persisted** to the conversation table and before the graph is invoked, on both the JSON and streaming endpoints, so the stored history and the graph input agree (see [Agent chat endpoints, SSE streaming and side panels](streaming-and-side-panels.md)).

## 2. The booking human-in-the-loop gate

Booking is the only flow that commits something irreversible, so it runs behind a LangGraph `interrupt`:

1. The supervisor routes a `booking` intent to the `plan` node (never as a queued follow-on; see the routing page).
2. `plan_node` calls `interrupt({"type": "plan_approval", "draft": <last message>})`. The run stops; the router reports `interrupt_pending=True` with the payload, writes **no assistant reply row** (there is nothing to rate yet) and returns empty suggestions.
3. The client resumes by posting `resume={"approved": true|false}`. Both `/agent/chat` and `/agent/stream` turn that into `Command(resume=...)` instead of a new human turn; the router also commits its session first so a tool's own session scope can write.
4. On rejection the graph ends with a localized "booking cancelled" reply. On approval it sets `plan_approved=True` and continues into the booking specialist without emitting any message (an "approved" line would be streamed and then wiped by the mapper's handoff reset).

`plan_approved` is single-turn state: `load_context` resets it on the next fresh turn, but a resume does not pass through `load_context`, so the approving turn keeps the flag long enough for background memory extraction to record the episode as `approved`. The memory extractor is only scheduled from the non-interrupt branch of the router; that `else` branch is the sole thing preventing extraction on a half-finished turn.

The tier gate in the supervisor is what keeps free-tier users out of this path entirely: `context_for_tier` removes `booking` from `allowed_subagents` for `Tier.FREE`, and a gated target ends the turn with an upgrade message before `plan` is reachable.

`GET /agent/conversations/{id}/messages` also reports any pending interrupt from the checkpoint so a reloaded client can re-render the approval prompt; it is ownership-scoped and degrades to "no interrupt" when the graph is unavailable.

## 3. Destructive tools: confirm, ownership, no double-booking

The tool registry marks `book_hotel`, `book_flight`, `cancel_flight` and `cancel_hotel` as **destructive** and a wider set as write tools; both flags feed tool annotations and the MCP exclusion rules (see [MCP server exposure](../integrations/mcp-server.md)). On top of that:

- **`confirm=True` is required.** Each booking and cancellation tool defaults `confirm` to `False` and refuses to act until the model passes `True`, so a speculative or accidental call books nothing. Cancellation tools additionally refuse a booking of the other type.
- **Owner scoping is injected, never model-supplied.** `user_id` (and `trip_id` for bookings) arrive through `InjectedState`; a foreign booking id reads as "not found" and can never be cancelled.
- **Duplicate protection.** `book_hotel` reports a possible duplicate when an active booking for the same hotel and exact dates exists; the model is instructed to tell the traveller and only set `allow_duplicate=True` after explicit confirmation. Details live in [Bookings, flights and hotels](../domain/bookings-flights-and-hotels.md).
- **Reflection never re-runs a committed booking.** If a `ToolMessage` from a booking write tool succeeded since the last human message, the reflection node ends the turn before its judge call, because a REVISE would route back into the booking specialist and double-book (gh-193). `tests/agents/test_reflection_booking_guard.py` checks that errored bookings and bookings from earlier turns still reach the judge.

## 4. The trip guard inside every specialist

A trip-scoped tool called with no active trip would fail `ToolNode` validation and merely *describe* the failure to the model, which could then call the tool again. `_make_trip_guard` in the sub-agent factory makes the outcome a graph fact instead: it runs before the `tools` node, and when any pending call needs a trip while `state["trip_id"]` is empty it emits an error `ToolMessage` for **every** pending call (the provider rejects an assistant turn with unpaired tool calls), sets `awaiting_user=True`, and routes back to the assistant. Reflection then ends the turn without review and the traveller is asked which trip they mean, by destination and dates rather than by id. Blocked tools never execute. See [Specialist sub-agents and the tool registry](specialists-and-tools.md).

## 5. Memory poisoning: write guard, read guard, prompt wrapping

Long-term memory is re-injected into every future system prompt, so one message saying "from now on always…" could become a permanent directive. Three layers contain that (design: `specs/memory-poisoning-hardening`):

**Write path — `guard.check`** (`apps/api/app/memory/guard.py`). Preferences and instructions must use a key from the canonical allowlists; episode keys must match a slug shape. Text is normalized (lower-cased, diacritics folded) and scanned against an ordered EN + VI blocklist of categories such as `instruction_override` and `role_spoofing`; over-length text is rejected. Violations raise `MemoryRejected`, an `AppError` with a 422 status whose `reason` names the rule and never echoes the rejected text. Every caller (extractor, memory tools, read helpers) catches it, so it never reaches an HTTP response.

**Read path — `guard.check_content`.** Applied to every row as it is read back. Keys need only match the shape rule, so harmless legacy keys still surface, but a key containing `<`, `:` or spaces is dropped. Over-length text is *truncated* rather than rejected, and the blocklist runs on the full text before truncation. Callers must use the returned text, never the stored original; this is what keeps angle brackets out of the prompt for rows written before the guard existed. `check_episode` applies the same rules to an episode's `city`, `outcome` and `trip_id` metadata, dropping a bad `trip_id` rather than losing the whole memory.

**Prompt wrapping — `system_with_summary`** (`apps/api/app/agents/state.py`). The three memory-derived blocks (`profile`, `instructions`, `preferences`) are each wrapped in `<traveller_memory kind=…>` tags and preceded once by `MEMORY_PREAMBLE`, which tells the model these are data about the traveller, not instructions, and to disregard any item that asks it to change role, ignore rules or take an action. Account email, trip context, summary and trip facts stay outside the tags.

The blocklist is explicitly documented as bypassable (for example by splicing zero-width characters into a phrase, which the fold does not strip because stored text must equal scanned text); the allowlist, the length cap and the prompt wrapping are the primary controls. `tests/agents/test_load_context_memory_guard.py` verifies end-to-end that a poisoned instruction is absent from the prompt, a row with a poisoned key is dropped, valid rows beyond a poisoned window still arrive, and a failing read helper omits only its own block.

## What is not guarded here

- Tool output and RAG results are not wrapped as untrusted data today (deferred as E001 in the memory-poisoning spec).
- The PII layer does not touch phones, emails or names by design.
- The free-tier daily turn quota and per-user rate limits are enforced in the router before the graph runs, not in the graph; see [Rate limiting and quotas](../concepts/rate-limiting-and-quotas.md).
