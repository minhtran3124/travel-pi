import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import en from "../../../../messages/en.json";
import { ProgressStepper } from "./ProgressStepper";

function renderStepper() {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <ProgressStepper
        subagents={[
          { name: "flights", status: "ok" },
          { name: "stays", status: "running" },
        ]}
        lastEval={{ iteration: 1, result: "pass", explanation: "Looks great, well sourced." }}
      />
    </NextIntlClientProvider>,
  );
}

describe("ProgressStepper", () => {
  it("shows the localized step list", () => {
    renderStepper();
    const p = en.TripDetail.research.progress;
    for (const label of [p.flights, p.stays, p.days, p.budget, p.entry, p.quality]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("never renders raw tool/subagent names, statuses, or the grader explanation", () => {
    renderStepper();
    // Raw streamed identifiers and the English grader text must not reach the DOM.
    expect(screen.queryByText("flights")).not.toBeInTheDocument();
    expect(screen.queryByText("entry_season")).not.toBeInTheDocument();
    expect(screen.queryByText("running")).not.toBeInTheDocument();
    expect(screen.queryByText("ok")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Looks great, well sourced."),
    ).not.toBeInTheDocument();
  });

  it("marks a step done once its dossier file is written, and the next one active", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <ProgressStepper
          subagents={[]}
          files={[
            { path: "/research/flights.md", bytes: 900 },
            { path: "/research/stays.md", bytes: 640 },
          ]}
          lastEval={null}
        />
      </NextIntlClientProvider>,
    );
    const states = screen
      .getAllByRole("listitem")
      .map((li) => li.getAttribute("data-state"));
    // flights, stays done → days is being worked on; budget, entry, quality wait.
    expect(states).toEqual(["done", "done", "active", "pending", "pending", "pending"]);
  });
});
