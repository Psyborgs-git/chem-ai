/** AT-0205-2 — a prediction and a measured result rendered side by
 * side must carry distinct evidence type + uncertainty/context
 * without color-only meaning. */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QuantityDisplay } from "./QuantityDisplay";

describe("QuantityDisplay evidence distinction (AT-0205-2)", () => {
  it("predicted and measured results expose different text + marker", () => {
    render(
      <div>
        <QuantityDisplay
          value="1.24"
          unit="Pa_s"
          basis="as_supplied"
          uncertainty="0.05"
          conditions="25 degC, 1 bar"
          evidence="predicted"
        />
        <QuantityDisplay
          value="1.31"
          unit="Pa_s"
          basis="as_supplied"
          uncertainty="0.02"
          conditions="25 degC, 1 bar"
          evidence="measured"
        />
      </div>,
    );
    const predicted = screen.getByText("predicted");
    const measured = screen.getByText("measured");
    expect(predicted).toBeInTheDocument();
    expect(measured).toBeInTheDocument();
    // distinct non-color identity: data attributes differ
    expect(predicted.closest("[data-evidence]")).toHaveAttribute(
      "data-evidence",
      "predicted",
    );
    expect(measured.closest("[data-evidence]")).toHaveAttribute(
      "data-evidence",
      "measured",
    );
    // uncertainty + conditions are inline at the result, not hidden
    expect(screen.getByText(/0\.05/)).toBeInTheDocument();
    expect(screen.getAllByText(/25 degC, 1 bar/)).toHaveLength(2);
  });

  it("an unknown value renders a dash with an accessible reason — never a zero", () => {
    render(<QuantityDisplay unit="Pa_s" evidence="measured" />);
    const note = screen.getByRole("note");
    expect(note).toHaveTextContent("—");
    expect(note).toHaveTextContent("unknown");
    expect(note).not.toHaveTextContent("0");
  });
});
