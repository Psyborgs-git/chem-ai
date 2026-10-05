/** AT-0205-1 — keyboard-only quantity + unit editing: focus order,
 * label association and validation must all be accessible. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { QuantityInput } from "./QuantityInput";

function Harness({ error }: { error?: string }) {
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("mass_fraction");
  return (
    <QuantityInput
      label="solvent amount"
      value={value}
      unit={unit}
      units={["mass_fraction", "mass_percent", "kg"]}
      basis="as_supplied"
      error={error}
      onValueChange={setValue}
      onUnitChange={setUnit}
    />
  );
}

describe("QuantityInput keyboard accessibility (AT-0205-1)", () => {
  it("tab order reaches value then unit; both fields are labeled", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const valueField = screen.getByLabelText("value");
    const unitField = screen.getByLabelText("unit");
    const group = screen.getByRole("group", { name: "solvent amount" });
    expect(group).toBeInTheDocument();

    await user.tab();
    expect(valueField).toHaveFocus();
    await user.tab();
    expect(unitField).toHaveFocus();
  });

  it("keyboard entry edits the value as a decimal string", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const valueField = screen.getByLabelText("value");
    await user.click(valueField);
    await user.keyboard("0.45");
    expect(valueField).toHaveValue("0.45");
  });

  it("keyboard selects a unit", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const unitField = screen.getByLabelText("unit");
    await user.click(unitField);
    await user.selectOptions(unitField, "mass_percent");
    expect(unitField).toHaveValue("mass_percent");
  });

  it("domain validation feedback is exposed via aria-invalid + alert", async () => {
    render(<Harness error="COMPOSITION_TOTAL_INVALID: total must be 1" />);
    const valueField = screen.getByLabelText("value");
    expect(valueField).toHaveAttribute("aria-invalid", "true");
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("COMPOSITION_TOTAL_INVALID");
    // the field references the message programmatically
    expect(valueField).toHaveAttribute(
      "aria-describedby",
      expect.stringContaining(alert.id),
    );
  });

  it("malformed input is rejected at the field with an accessible message", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const valueField = screen.getByLabelText("value");
    await user.click(valueField);
    await user.keyboard("abc");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter a decimal number.",
    );
    expect(valueField).toHaveValue("");
  });

  it("basis is announced next to the value, not hidden", () => {
    render(<Harness />);
    expect(screen.getByText("basis: as_supplied")).toBeInTheDocument();
  });
});
