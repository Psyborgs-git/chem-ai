import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, it, vi } from "vitest";
import { UnitSelect } from "./UnitSelect";

it("preserves the domain's missing-unit choice when selecting or clearing a unit", async () => {
  const change = vi.fn();
  function Harness() {
    const [unit, setUnit] = useState("");
    return <UnitSelect label="Measurement unit" units={["", "g", "kg"]} value={unit} onValueChange={(value) => { change(value); setUnit(value); }} />;
  }
  render(<Harness />);
  const trigger = screen.getByRole("combobox", { name: "Measurement unit" });
  expect(trigger).toHaveTextContent("Not specified");
  await userEvent.click(trigger);
  await userEvent.click(await screen.findByRole("option", { name: "g" }));
  expect(change).toHaveBeenLastCalledWith("g");
  await userEvent.click(trigger);
  await userEvent.click(await screen.findByRole("option", { name: "Not specified" }));
  expect(change).toHaveBeenLastCalledWith("");
  expect(trigger).toHaveTextContent("Not specified");
});
