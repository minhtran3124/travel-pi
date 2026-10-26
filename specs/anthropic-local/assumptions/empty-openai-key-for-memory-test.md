# OPENAI_API_KEY empty to test memory extraction

PR #275, issue #270. Source: test:memory-cost.

## Assumption &middot; PR #275 &middot; issue #270</div><h1>OPENAI_API_KEY empty to test memory extraction</h1></div><div class="card"><div class="lab">Context

The OpenAI embeddings credit is exhausted, so memory writes return 429.

## Decision

Ran the server with an empty OPENAI_API_KEY to trigger the fake-embeddings fallback. This isolates the Haiku extraction logic from the embeddings dependency.

## Alternatives

Mark the memory case as skipped.

## Impact if wrong

Extraction and store writes are verified. Semantic recall quality is not.

## How to reverse

Restore OpenAI credit, then re-run the memory case with real embeddings.

