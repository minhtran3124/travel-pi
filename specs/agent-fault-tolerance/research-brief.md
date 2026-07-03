# Research Brief — MIN-49 Agent Fault-Tolerance

**Depth:** Deep (agent runtime + provider-SDK integration behavior).
**Feature:** Adopt LangGraph `RetryPolicy` + node `error_handler` for the agent
graph, gated behind transient-vs-logic tool-error classification. See
`design.md`.

> **PROJECT.md caveat:** the xia2 `PROJECT.md` at `.claude/skills/xia2/PROJECT.md`
> is the **harness meta-repo template** (references `scripts/run-tests.sh`,
> `hooks/*.sh`, `skills/*/SKILL.md` — none exist in travel-pi). Known-wrong for
> this repo (memory: `specs-tracked-not-gitignored`). Depth was classified **Deep**
> from concrete signals (agent graph + provider-SDK behavior), not template
> mappings — so the config gate's intent (no guessed classification) is met.

## 1. Stack (from manifests — `Local`)

- Python 3.14 local / 3.12 Docker. FastAPI backend in `apps/api/`.
- `apps/api/requirements-ai.txt`: `langgraph>=1.0,<2.0`, `langchain>=1.0,<2.0`,
  `langchain-openai>=0.3,<1.0`, `langchain-anthropic>=1.0,<2.0`,
  `langchain-google-genai>=4.0,<5.0`.
- **Installed (verified):** `langgraph==1.2.6`, `langchain==1.3.11`,
  `langchain-openai==0.3.34`, `langchain-anthropic` present. (Ticket said 1.1.6 —
  actual is 1.2.6, within pin.)
- **No new dependency required** — `RetryPolicy` / `error_handler` / `NodeError`
  are built into langgraph. No `tenacity`, no SDK imports.

## 2. Open item 1 — provider-SDK exceptions for `LLM_RETRY.retry_on`

**`Local` — the hard constraint.** `app/clients/llm.py` builds every model via
`init_chat_model(model, model_provider=profile.sdk, streaming=True, ...)` and its
docstring states the design rule: *"The agent layer never imports a provider SDK
directly."* Providers are multi: `openai`, `anthropic`, `google_genai`,
`clinepass` (OpenAI-compatible gateway). **Therefore `LLM_RETRY.retry_on` must NOT
`import openai`/`anthropic`** — it has to duck-type.

**`Docs`/`Inference` — what surfaces.** The OpenAI SDK raises `RateLimitError`
(429), `APITimeoutError`, `APIConnectionError`, `InternalServerError` (5xx),
`APIStatusError` (carries `.status_code` / `.response`); Anthropic mirrors this.
These are **not** subclasses of `httpx.HTTPStatusError` or `ConnectionError`.

**`Local` — langgraph's `default_retry_on` is too permissive for LLM.** Verified
source (`langgraph/types.py`): it retries `ConnectionError`, `httpx`/`requests`
5xx, blocklists `ValueError`/`TypeError`/`Lookup…`, and **returns `True` for
everything else** — so it would retry a non-retryable `BadRequestError` (400) too.
Not safe to rely on as-is for LLM.

**Recommendation (`Inference`):** a provider-agnostic predicate —
```python
def _is_retryable_llm(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None)
    if code in (408, 409, 429) or (isinstance(code, int) and 500 <= code < 600):
        return True
    return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, ConnectionError)) \
        or exc.__class__.__name__ in {"APIConnectionError", "APITimeoutError", "APIConnectionTimeoutError"}
```
Duck-types on `.status_code` + class-name + httpx base — zero provider imports.

### ⚠️ MAJOR finding — LLM retry overlaps with SDK-level retry (needs a user decision)

**`Local`, verified.** `langchain-openai` `max_retries` default = `None` → falls
back to the OpenAI SDK's own `DEFAULT_MAX_RETRIES = 2`; `langchain-anthropic`
`max_retries` default = **2**. **Both providers already retry 429 / 5xx /
connection errors ~2× with backoff inside `.invoke()`** before any exception
escapes to the graph. `app/clients/llm.py` does **not** override `max_retries`.

Consequence: a graph-level `LLM_RETRY(max_attempts=3)` **stacks on top** → up to
~2×3 = 6 underlying attempts on a sustained outage. Meanwhile the **tools path
(`weather_service` / `routing_service`) has NO retry at all** (verified: no
`retry`/`tenacity`/`max_retries` in either service) — that is the genuine,
non-redundant gap.

**Options to resolve before planning:**
- **(A) Tools-focused (recommended):** apply graph `RetryPolicy` to the **tools**
  path only (the real gap); for LLM, rely on / lightly tune the SDK's built-in
  retry (e.g. pass `max_retries` through `_build_chat_model`). Avoids retry-stacking;
  smaller diff. **Trades away** the "uniform graph-level LLM retry" the user picked.
- **(B) Uniform + de-stack:** keep graph `LLM_RETRY` on all LLM nodes (as chosen)
  **but** set the SDK `max_retries=0` in `_build_chat_model` so retry lives in one
  place (the graph). One clear retry owner; touches `clients/llm.py` (a shared
  runtime contract — Deep).
- **(C) Accept overlap:** graph `LLM_RETRY` on top of SDK retry, bounded by
  `max_attempts` + `max_interval=128s`. Simplest to write; worst-case latency/cost
  amplification on a real outage.

This is the one item that materially revisits the "all real LLM calls" decision —
surface to the user (see §6).

## 3. Open item 2 — `NodeError` + `error_handler` (CONFIRMED, `Local`)

Verified against installed `langgraph/errors.py`:
```python
@dataclass(frozen=True, slots=True)
class NodeError:
    node: str          # failed node name
    error: BaseException
```
Its own docstring shows the exact handler shape:
```python
def handler(state: State, error: NodeError) -> Command:
    return Command(update={...})   # read error.error
```
- Import: `from langgraph.errors import NodeError`.
- `add_node(..., error_handler=<callable>)` is a valid param (langgraph 1.2.6).
- Handler receives `(state, error)`, **not** `(state, exc)` — the design's fix is
  correct. Read the exception via `error.error`.

## 4. Open item 3 — ToolNode annotation-narrowing (CONFIRMED, `Local`)

Verified `langgraph/prebuilt/tool_node.py`: when `handle_tool_errors` is a
callable, `handled_types = _infer_handled_types(handler)` (from the first-param
annotation), then:
```python
if not self._handle_tool_errors or not isinstance(e, handled_types):
    raise
```
So annotating the handler `exc: ToolException` sets `handled_types=(ToolException,)`;
a re-raised `UpstreamError` (not a `ToolException`) fails `isinstance` → **`raise`
→ propagates** to the node → `RetryPolicy`. Confirmed the design mechanism works.

**`RetryPolicy` is a `NamedTuple`** (`langgraph/types.py`) with defaults
`initial_interval=0.5, backoff_factor=2.0, max_interval=128.0, max_attempts=3,
jitter=True` — **exactly** the design's proposed params. So `LLM_RETRY` /
`TRANSIENT_RETRY` only need to override `retry_on` (keep the rest as defaults).

## 5. Lightest credible path

**Reuse built-ins > adapt > build.** Everything needed ships in langgraph 1.2.6:
`RetryPolicy` (defaults already match), `error_handler` + `NodeError`, ToolNode
annotation-narrowing. **No new dependency, no provider-SDK import.** The only net-new
code is `app/agents/retry.py` (2 policies + 1 handler + 1 duck-typed predicate) and
the wiring/tool edits enumerated in `design.md §4.3`. `BookingService.cancel()`
exists but is intentionally unused (SAGA dropped).

## 6. Deltas to fold back before `/writing-plans`

1. **Version:** design refs updated 1.1.6 → **1.2.6** (done in design.md).
2. **`retry_on` predicate:** add the duck-typed `_is_retryable_llm` to design.md
   §4.3 (no SDK import); `TRANSIENT_RETRY.retry_on = isinstance UpstreamError`.
   Keep all other `RetryPolicy` fields at defaults (they already match).
3. **DECISION NEEDED — LLM retry overlap (§2):** the SDK already retries LLM calls
   ~2×. Choose (A) tools-focused / (B) uniform + SDK `max_retries=0` / (C) accept
   overlap. (B) or (A) recommended; (B) keeps the user's "all LLM calls" intent with
   one retry owner but edits the shared `clients/llm.py` contract (Deep).
4. **`error_handler` signature** confirmed `(state, error: NodeError)` — already
   fixed in design.md.
