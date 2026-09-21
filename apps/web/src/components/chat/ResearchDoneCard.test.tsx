import { fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "../../../messages/en.json";
import vi_ from "../../../messages/vi.json";
import type { ResearchRunSummary } from "@/lib/api/research";

const api = vi.hoisted(() => ({ getResearchFile: vi.fn() }));
vi.mock("@/lib/api/research", () => api);
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
  beforeEach(() => api.getResearchFile.mockReset());

  it("shows the agent's summary and points to the details", async () => {
    api.getResearchFile.mockResolvedValue(
      "- Cheapest flight: 1.2M VND, morning\n- Stay near Duong Dong night market",
    );
    renderCard("en", { ...RUN, files: [...RUN.files, "summary.md"] });

    const summary = await screen.findByTestId("research-summary");
    expect(api.getResearchFile).toHaveBeenCalledWith("run-1", "summary.md");
    expect(
      within(summary).getAllByRole("listitem").map((li) => li.textContent),
    ).toEqual([
      "Cheapest flight: 1.2M VND, morning",
      "Stay near Duong Dong night market",
    ]);
    expect(screen.queryByText(en.Chat.researchDone.hint)).toBeNull();
    // The summary walks through the sections, so the chips step aside.
    expect(screen.queryByTestId("research-chips")).toBeNull();
    expect(
      screen.getByRole("link", { name: /See all the details/ }),
    ).toHaveAttribute("href", "/trips/trip-1?tab=research");
  });

  it("keeps the hint when the summary cannot be read", async () => {
    api.getResearchFile.mockRejectedValueOnce(new Error("404"));
    renderCard("en", { ...RUN, files: [...RUN.files, "summary.md"] });

    await new Promise((r) => setTimeout(r, 0));
    expect(api.getResearchFile).toHaveBeenCalledTimes(1);
    expect(screen.getByText(en.Chat.researchDone.hint)).toBeInTheDocument();
    expect(screen.queryByTestId("research-summary")).toBeNull();
  });

  it("does not fetch a summary the dossier does not have", () => {
    renderCard("en");
    expect(api.getResearchFile).not.toHaveBeenCalled();
  });

  it("lists what the research covers as chips and links to the Research tab", () => {
    renderCard("en");

    expect(screen.getByText(en.Chat.researchDone.title)).toBeInTheDocument();
    expect(screen.getByText(en.Chat.researchDone.hint)).toBeInTheDocument();
    expect(
      within(screen.getByTestId("research-chips")).getAllByRole("listitem").map((li) => li.textContent),
    ).toEqual([
      "📅 2-day plan",
      "✈️ Flights",
      "🏨 Stays",
      "🛂 Entry & best time",
      "💰 Budget",
    ]);
    expect(
      screen.getByRole("link", { name: /See the research/ }),
    ).toHaveAttribute("href", "/trips/trip-1?tab=research");
  });

  it("renders in Vietnamese", () => {
    renderCard("vi");

    expect(screen.getByText(vi_.Chat.researchDone.title)).toBeInTheDocument();
    expect(
      within(screen.getByTestId("research-chips")).getAllByRole("listitem").map((li) => li.textContent),
    ).toEqual([
      "📅 Lịch trình 2 ngày",
      "✈️ Chuyến bay",
      "🏨 Chỗ ở",
      "🛂 Thủ tục & mùa đẹp",
      "💰 Ngân sách",
    ]);
  });

  it("uses the no-plan hint and no chips when the dossier has nothing to list", () => {
    renderCard("en", { ...RUN, files: ["overview.md"], proposal_ready: false });

    expect(screen.getByText(en.Chat.researchDone.hintNoPlan)).toBeInTheDocument();
    expect(screen.queryByTestId("research-chips")).toBeNull();
  });

  it("dismisses from the close button and from opening the tab", () => {
    const onDismiss = renderCard("en");

    fireEvent.click(screen.getByRole("button", { name: en.Chat.researchDone.dismiss }));
    const link = screen.getByRole("link", { name: /See the research/ });
    link.addEventListener("click", (e) => e.preventDefault()); // jsdom cannot navigate
    fireEvent.click(link);

    expect(onDismiss).toHaveBeenCalledTimes(2);
  });
});
