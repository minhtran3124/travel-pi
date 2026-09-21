import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import en from "../../../messages/en.json";
import vi_ from "../../../messages/vi.json";
import type { ResearchRunSummary } from "@/lib/api/research";
import { dossierSections, ResearchDoneCard } from "./ResearchDoneCard";

const RUN: ResearchRunSummary = {
  run_id: "run-1",
  trip_id: "trip-1",
  status: "completed",
  thread_turn: 1,
  files: [
    "budget.md",
    "days/day-1.md",
    "days/day-2.md",
    "entry-and-season.md",
    "flights.md",
    "overview.md",
    "proposal.json",
    "stays.md",
  ],
  proposal_ready: true,
};

function renderCard(
  locale: "en" | "vi",
  run: ResearchRunSummary = RUN,
  onDismiss = vi.fn(),
) {
  render(
    <NextIntlClientProvider locale={locale} messages={locale === "en" ? en : vi_}>
      <ResearchDoneCard run={run} tripId="trip-1" onDismiss={onDismiss} />
    </NextIntlClientProvider>,
  );
  return onDismiss;
}

describe("dossierSections", () => {
  it("reads sections and day count from the file index, ignoring other files", () => {
    expect(dossierSections(RUN.files)).toEqual({
      sections: ["flights", "stays", "entry", "budget"],
      days: 2,
    });
  });

  it("accepts leading slashes", () => {
    expect(dossierSections(["/flights.md", "/days/day-1.md"])).toEqual({
      sections: ["flights"],
      days: 1,
    });
  });
});

describe("ResearchDoneCard", () => {
  it("summarizes the dossier and links to the Research tab", () => {
    renderCard("en");

    expect(screen.getByText(en.Chat.researchDone.title)).toBeInTheDocument();
    expect(
      screen.getByText(
        "The dossier covers a 2-day plan · flights · stays · entry & season · budget.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(en.Chat.researchDone.proposalReady)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: en.Chat.researchDone.open }),
    ).toHaveAttribute("href", "/trips/trip-1?tab=research");
  });

  it("renders in Vietnamese", () => {
    renderCard("vi");

    expect(screen.getByText(vi_.Chat.researchDone.title)).toBeInTheDocument();
    expect(
      screen.getByText(
        "Hồ sơ gồm lịch trình 2 ngày · chuyến bay · chỗ ở · nhập cảnh & mùa · ngân sách.",
      ),
    ).toBeInTheDocument();
  });

  it("omits the proposal line and the covers line when there is nothing to list", () => {
    renderCard("en", { ...RUN, files: ["overview.md"], proposal_ready: false });

    expect(screen.queryByText(en.Chat.researchDone.proposalReady)).toBeNull();
    expect(screen.queryByText(/The dossier covers/)).toBeNull();
  });

  it("dismisses from the close button and from opening the tab", () => {
    const onDismiss = renderCard("en");

    fireEvent.click(screen.getByRole("button", { name: en.Chat.researchDone.dismiss }));
    const link = screen.getByRole("link", { name: en.Chat.researchDone.open });
    link.addEventListener("click", (e) => e.preventDefault()); // jsdom cannot navigate
    fireEvent.click(link);

    expect(onDismiss).toHaveBeenCalledTimes(2);
  });
});
