# Assumption: Isolation for multi-call batches

## Context
If the tools node raises, the node-level graceful_fallback degrades every pending call and loses results from calls that already succeeded. Node-level RetryPolicy would re-run committed calls.

## Decision
For batches with more than one call, run each call separately and concurrently, with up to 3 attempts for upstream faults and an error ToolMessage for any call that still fails. Single-call turns keep the existing RetryPolicy and error_handler path.

## Alternatives
Wrap the tools in tool-level try/except; or keep the node-level path and make every tool idempotent.

## Impact if wrong
No backoff between attempts in the isolated path. A side-effecting tool runs once per call. If wrong, a transient fault may fail faster than before.

## How to reverse
Revert the batch branch so all turns use the node-level path again. No stored data is affected.
