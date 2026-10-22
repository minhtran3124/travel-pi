---
problem_type: failure
module: harness
tags: verification, gates, false-green, vitest, negative-control, mutation-testing, review-methodology, evidence
severity: critical
applicable_when: Adding or reviewing any check that is supposed to protect something — a task Verify, a Success Criterion, a CI gate, a lint rule, or a test written to close a review finding. Above all when the check is new and has only ever been seen green.
affects:
  - apps/web/src/lib/i18n/langParam.seed.test.ts
  - apps/web/src/lib/i18n/langParam.suppression.test.ts
  - apps/web/src/i18n/no-hardcoded-strings.test.ts
  - apps/web/src/app/bookings/page.test.tsx
  - specs/review-c3-web-ssr-i18n/PLAN.md
supersedes: null
confidence: high
confirmed_at: 2026-09-08

---
## Applicable When

Adding or reviewing any check that is supposed to protect something — a task `Verify`, a Success
Criterion, a CI gate, a lint rule, or a test written to close a review finding. Above all when the
check is new and has only ever been seen green.

## Symptom

A gate is green. The thing it names is not actually protected. Nothing looks wrong, because a
passing check and a vacuous check are indistinguishable from the outside — which is exactly why
this survives review.

One slice produced **seven** instances. They are listed because the variety is the lesson: this is
not one mistake, it is a shape that keeps finding new ways in.

| # | The check | Why it proved nothing |
|---|---|---|
| 1 | `vitest run <file> -t "<name>"` | A `-t` filter matching no test name **exits 0**. Rename the block, gate goes green forever. |
| 2 | `vitest run fileA fileB` | A multi-filter run exits 0 when only `fileA` matches. One of the two files could be absent. |
| 3 | `messages.parity.test.ts` cited as proof six keys were added | It compares the two catalogs *to each other*. It passes on a tree where none of the six keys exists. |
| 4 | "writes the cookie with `setUserLocale`'s attributes" | The test asserted only `cookie.value`. `path`, `maxAge` and `sameSite` could all change and stay green. |
| 5 | "the live region uses the catalog key, not a literal" | `next-intl` is mocked as identity, and no test asserted the rendered text. Hardcoding English passed. |
| 6 | Suppression cases named `row 1`, `row 2`, `row 3` | They asserted only that the session cookie survived — which row 5 also does. A guard falling through to row 5 left all three green while the named branch was never taken. |
| 7 | A gate for hardcoded `aria-label`s | Its regex matched `aria-label="x"` only, missing `aria-label={"x"}`, `{'x'}` and `` {`x`} `` — three of four spellings, including the one written when converting to or from `t()`. |

## Wrong Approach

Reading the check and judging that it looks right. Every one of the seven passed that bar, several
times: five rounds of adversarial document review over a design, three rounds over a plan, and
per-task reviews on every wave. Reviewers verified line numbers, exports, counts and command
syntax — all correctly — and still could not see that the commands proved nothing, because the
defect is not visible in the text of the check.

Also wrong: treating a green run as evidence the check works. A check has two possible states and
you have only ever observed one of them.

## Why It Failed

A check has a claim and a mechanism, and reading only tells you about the claim. Nothing in
`vitest run x.test.ts -t "seeds"` says it exits 0 on no match; nothing in a parity test says it is
symmetric; nothing in `expect(cookie.value).toBe("vi")` announces the three attributes it ignores.
Every one of these was found by *running* something — a probe, a mutation, an injected leak — and
none by reading.

The pattern also mutates. Fixing form 1 (`-t` filters) reintroduced the same defect as form 2
(multi-filters) in the same document, because the fix addressed the instance rather than the shape.

## Correct Approach

**A new gate is not finished until it has been observed red.** Break the thing it protects, watch
it fail, restore, and record what you broke. Treat that negative control as part of the deliverable,
not as optional diligence.

Concretely, and all of these caught something real here:

- **One file per criterion.** A single filter naming a missing file exits 1; a directory filter or
  a multi-file filter exits 0 on a partial match. Chain single-file runs with `&&`.
- **Mutate the implementation, not the test.** Shorten a `maxAge`, flip a `sameSite`, delete a
  cookie-copy loop, make a guard fall through to the next branch. Each mutation should turn exactly
  one check red. If it turns none red, that check is decoration.
- **Inject the real defect into a real file**, not only into an inline fixture. A gate that catches
  its own fixture may still miss the tree it scans.
- **Ask what else satisfies the assertion.** "The cookie survived" is satisfied by the branch you
  meant *and* by the branch you did not. Name the discriminator.
- **Per-detector positive controls.** A gate with two detectors needs each to prove its own scanned
  count is non-zero. A shared count lets the broad detector satisfy the assertion on behalf of a
  narrow one whose glob matched nothing.

A false-positive fix deserves the same suspicion. Broadening the `aria-label` regex here made it
fire on a legitimately templated label built from `t()`; the fix for *that* could easily have blinded
the detector again. Verify a precision fix against the real codebase, not against the fixture.

## Guardrail

`proposed:` A plan lint that rejects a `Verify` or Success-Criteria command containing `vitest`
together with `-t `, a bare directory path, or more than one positional file filter — the three
forms measured to exit 0 without asserting anything. Target: `.claude/scripts/check_plan_contract.py`.

## Related
- docs/solutions/harness/negative-grep-is-not-absence.md
- docs/solutions/harness/verify-against-invented-rule.md
