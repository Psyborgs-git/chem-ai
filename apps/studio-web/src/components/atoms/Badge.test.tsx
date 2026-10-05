/** §22.3 — evidence badges are a different axis from completion
 * badges; both must read as text, not color. */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge } from "./Badge";
import { EvidenceTypeLabel } from "./EvidenceTypeLabel";
import { StatusIndicator } from "./StatusIndicator";

describe("evidence vs status axes", () => {
  it("evidence kinds and workflow statuses are different DOM axes", () => {
    render(
      <div>
        <EvidenceTypeLabel kind="measured" />
        <StatusIndicator status="completed" />
        <Badge tone="success">approved</Badge>
      </div>,
    );
    const evidence = screen.getByText("measured").closest("[data-evidence]");
    const status = screen.getByText("completed").closest("[data-status]");
    expect(evidence).toHaveAttribute("data-evidence", "measured");
    expect(status).toHaveAttribute("data-status", "completed");
    // the two axes cannot collide: evidence has no data-status attr
    expect(evidence).not.toHaveAttribute("data-status");
    expect(status).not.toHaveAttribute("data-evidence");
    expect(screen.getByText("approved")).toBeInTheDocument();
  });
});
