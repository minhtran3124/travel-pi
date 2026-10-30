import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import en from "../../../messages/en.json";
import vi from "../../../messages/vi.json";
import { PanelIntlProvider } from "@/components/chat/panel/PanelIntlProvider";
import { SimulatedDataNote } from "./SimulatedDataNote";

describe("SimulatedDataNote", () => {
  it("renders the English note", () => {
    render(
      <PanelIntlProvider language="en">
        <SimulatedDataNote />
      </PanelIntlProvider>,
    );
    expect(screen.getByRole("note")).toHaveTextContent(en.Panel.simulatedData);
  });

  it("renders the Vietnamese note", () => {
    render(
      <PanelIntlProvider language="vi">
        <SimulatedDataNote />
      </PanelIntlProvider>,
    );
    expect(screen.getByRole("note")).toHaveTextContent(vi.Panel.simulatedData);
  });
});
