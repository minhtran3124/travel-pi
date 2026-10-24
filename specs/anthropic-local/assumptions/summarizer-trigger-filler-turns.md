# Summarizer trigger with large filler turns

PR #275, issue #270. Source: test:memory-cost.

## Assumption &middot; PR #275 &middot; issue #270</div><h1>Summarizer trigger with large filler turns</h1></div><div class="card"><div class="lab">Context

The threshold is 20 messages, or about 10.2k estimated tokens with more than 5 messages. Reaching 20 messages would be costly.

## Decision

Used two turns of about 25k characters each to cross the token branch.

## Alternatives

Many short turns.

## Impact if wrong

Only the token branch of should_summarize ran. The message-count branch was not exercised.

## How to reverse

Add a cheap unit test for the count branch with a stubbed LLM.

