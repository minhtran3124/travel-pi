import { describe, expect, it } from "vitest";

import {
  AlreadyShortlistedError,
  ConflictError,
  DuplicatePlaceError,
  OverBudgetError,
  throwOn409,
} from "./errors";

describe("throwOn409 (existing call sites unchanged)", () => {
  it.each([
    ["OverBudgetError", OverBudgetError],
    ["DuplicatePlaceError", DuplicatePlaceError],
    ["AlreadyShortlistedError", AlreadyShortlistedError],
  ])("still throws %s as a ConflictError on a 409 response", (_name, Ctor) => {
    const response = new Response(null, { status: 409 });
    expect(() => throwOn409(response, { message: "Conflict" }, Ctor)).toThrow(
      Ctor,
    );
    try {
      throwOn409(response, { message: "Conflict" }, Ctor);
    } catch (err) {
      expect(err).toBeInstanceOf(ConflictError);
    }
  });

  it("does not throw for a non-409 response", () => {
    const response = new Response(null, { status: 403 });
    expect(() =>
      throwOn409(response, { message: "Forbidden" }, OverBudgetError),
    ).not.toThrow();
  });
});
