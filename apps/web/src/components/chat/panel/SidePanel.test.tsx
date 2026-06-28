import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SidePanel } from "./SidePanel";

describe("SidePanel", () => {
  it("renders nothing when no panel has a registered renderer (forward-compat)", () => {
    const { container } = render(
      <SidePanel
        panels={[{ toolCallId: "t1", kind: "weather", data: {} }]}
        onClose={() => undefined}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing for an empty panel list", () => {
    const { container } = render(
      <SidePanel panels={[]} onClose={() => undefined} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
