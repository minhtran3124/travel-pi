// Shared domain errors for BE conflict (409) and premium-gate (403) responses.
//
// The BE signals recoverable conflicts with a 409 and an optional `hint`. The FE
// raises a typed error so callers can show a friendly, non-crashing notice and,
// where useful, branch on the specific conflict via `instanceof`. The named
// subclasses keep those `instanceof` checks readable at call sites.

interface ApiError {
  message: string;
  hint?: string | null;
}

/** Base for every hint-carrying error surfaced to the UI. Carries the BE `hint`. */
export class HintedError extends Error {
  readonly hint?: string;
  constructor(message: string, hint?: string) {
    super(message);
    // `new.target` resolves to the concrete subclass, so each error reports its
    // own name without every subclass repeating a `this.name = ...` line.
    this.name = new.target.name;
    this.hint = hint;
  }
}

/** Base for every 409 conflict surfaced to the UI. Carries the BE `hint`. */
export class ConflictError extends HintedError {}

/** A linked booking would push the trip over a budget cap (POST item). */
export class OverBudgetError extends ConflictError {}

/** The place is already saved (POST /places/saved). */
export class DuplicatePlaceError extends ConflictError {}

/** The place is already on the trip's shortlist (POST /trips/{id}/places). */
export class AlreadyShortlistedError extends ConflictError {}

/** The caller's tier does not allow booking (POST /flights/book, /hotels/book). */
export class PremiumRequiredError extends HintedError {}

/**
 * Throw `Ctor` when `response` is a 409, carrying the BE message + hint.
 * No-op for any other status, so callers fall through to their generic
 * `throw error`. Collapses the repeated 409-branch boilerplate to one line.
 */
export function throwOn409(
  response: Response,
  error: ApiError,
  Ctor: new (message: string, hint?: string) => ConflictError,
): void {
  if (response.status === 409) {
    throw new Ctor(error.message, error.hint ?? undefined);
  }
}

/**
 * Throw `Ctor` when `response` is a 403, carrying the BE message + hint.
 * No-op for any other status, so callers fall through to their generic
 * `throw error`. Mirrors `throwOn409`.
 */
export function throwOn403(
  response: Response,
  error: ApiError,
  Ctor: new (message: string, hint?: string) => PremiumRequiredError,
): void {
  if (response.status === 403) {
    throw new Ctor(error.message, error.hint ?? undefined);
  }
}
