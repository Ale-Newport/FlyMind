import { describe, expect, it } from "vitest";
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { EvidenceBadge, ErrorBox, KV, Seg, SyntheticBanner } from "../../src/components/ui";
import { ICON_NAMES, Icon } from "../../src/components/Icon";
import { BackendRequiredError } from "../../src/lib/api";

describe("evidence badges", () => {
  it("label every evidence category with an explanation", () => {
    for (const kind of ["published", "reproduced", "simulation_output", "hypothesis", "demonstration"] as const) {
      const { unmount } = render(<EvidenceBadge kind={kind} />);
      const el = screen.getByTestId(`evidence-${kind}`);
      expect(el.getAttribute("title")?.length).toBeGreaterThan(10);
      unmount();
    }
  });
  it("renders nothing for unknown categories", () => {
    const { container } = render(<EvidenceBadge kind={null} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("notices", () => {
  it("flags synthetic data", () => {
    render(<SyntheticBanner show />);
    expect(screen.getByRole("note").textContent).toMatch(/synthetic/i);
  });
  it("explains backend-only features instead of failing silently", () => {
    render(<ErrorBox error={new BackendRequiredError("/api/sim/sessions")} />);
    expect(screen.getByRole("alert").textContent).toMatch(/local FlyMind backend/);
  });
});

describe("evidence marks", () => {
  it("combine a coloured shape with the category name (not colour alone)", () => {
    render(<EvidenceBadge kind="hypothesis" />);
    const el = screen.getByTestId("evidence-hypothesis");
    expect(el.textContent).toBe("Hypothesis");
    expect(el.querySelector("svg")).not.toBeNull();
  });
});

describe("icon set", () => {
  it("draws every icon on the 16px grid and hides it from assistive tech", () => {
    for (const name of ICON_NAMES) {
      const { container, unmount } = render(<Icon name={name} />);
      const svg = container.querySelector("svg")!;
      expect(svg.getAttribute("viewBox")).toBe("0 0 16 16");
      expect(svg.getAttribute("aria-hidden")).toBe("true");
      expect(svg.children.length).toBeGreaterThan(0);
      unmount();
    }
  });
});

describe("segmented control", () => {
  function Demo() {
    const [v, setV] = useState("a");
    return <Seg kind="radio" label="Choice" value={v} onChange={setV} options={[{ value: "a", label: "Alpha" }, { value: "b", label: "Beta" }]} />;
  }
  it("is a radiogroup with one checked radio and arrow-key selection", () => {
    render(<Demo />);
    expect(screen.getByRole("radiogroup", { name: "Choice" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "Alpha" }).getAttribute("aria-checked")).toBe("true");
    screen.getByRole("radio", { name: "Alpha" }).focus();
    fireEvent.keyDown(screen.getByRole("radio", { name: "Alpha" }), { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: "Beta" }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("radio", { name: "Alpha" }).getAttribute("aria-checked")).toBe("false");
  });
});

describe("key-value list", () => {
  it("sets units apart from values and skips empty rows", () => {
    render(<KV rows={[["Speed", "12", "mm/s"], false, ["Height", "–", "mm"]]} />);
    expect(screen.getAllByRole("term").length).toBe(2);
    expect(screen.getByText("mm/s").className).toContain("unit");
    expect(screen.queryByText("mm")).toBeNull(); // no unit after a missing value
  });
});
