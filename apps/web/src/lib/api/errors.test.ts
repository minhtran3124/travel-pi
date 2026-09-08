import { describe, expect, it } from "vitest";

import {
  AlreadyShortlistedError,
  ConflictError,
  DuplicatePlaceError,
  HintedError,
  OverBudgetError,
  PremiumRequiredError,
  throwOn403,
  throwOn409,
} from "./errors";

describe("throwOn403", () => {
  it("throws the given ctor, carrying message + hint, on a 403 response", () => {
    const response = new Response(null, { status: 403 });
    expect(() =>
      throwOn403(
        response,
        { message: "Premium plan required", hint: "Upgrade to book" },
        PremiumRequiredError,
      ),
    ).toThrow(PremiumRequiredError);

    try {
      throwOn403(
        response,
        { message: "Premium plan required", hint: "Upgrade to book" },
        PremiumRequiredError,
      );
    } catch (err) {
      expect(err).toBeInstanceOf(PremiumRequiredError);
      expect(err).toBeInstanceOf(HintedError);
      expect((err as PremiumRequiredError).message).toBe(
        "Premium plan required",
      );
      expect((err as PremiumRequiredError).hint).toBe("Upgrade to book");
    }
  });

  it("does not throw for a non-403 response (e.g. 404)", () => {
    const response = new Response(null, { status: 404 });
    expect(() =>
      throwOn403(
        response,
        { message: "Flight not found" },
        PremiumRequiredError,
      ),
    ).not.toThrow();
  });
});

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
