import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvidenceBadge, ErrorBox, SyntheticBanner } from "../../src/components/ui";
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
    expect(screen.getByRole("note").textContent).toMatch(/SYNTHETIC/);
  });
  it("explains backend-only features instead of failing silently", () => {
    render(<ErrorBox error={new BackendRequiredError("/api/sim/sessions")} />);
    expect(screen.getByRole("alert").textContent).toMatch(/local FlyMind backend/);
  });
});
