import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CampaignDefinitionEditor } from "./CampaignDefinitionEditor";

const SPEC = {
  parameters: [{ name: "loading", kind: "discrete", unit: "percent_m/m", values: ["0", "100"] }],
  target: { name: "metric.index", mode: "maximize", unit: "dimensionless", method: "reviewed-v1" },
  constraints: [{ parameters: ["loading"], coefficients: ["1"], operator: "<=", rhs: "75" }],
  context: { grade: "A", process: "B" }, seed: 17, recommender: "two_phase",
};
function Harness() {
  const [value, setValue] = useState(JSON.stringify(SPEC));
  return <><CampaignDefinitionEditor value={value} onChange={setValue} /><output data-testid="payload">{value}</output></>;
}

describe("Campaign contract editing", () => {
  it("retains constraints and context while changing a parameter representation", async () => {
    const user = userEvent.setup(); render(<Harness />);
    await user.selectOptions(screen.getByLabelText("Parameter type"), "categorical");
    await user.type(screen.getByLabelText("Categories"), "A, B");
    const result = JSON.parse(screen.getByTestId("payload").textContent!);
    expect(result.parameters[0]).toEqual({ name: "loading", unit: "percent_m/m", kind: "categorical", categories: ["A", "B"] });
    expect(result.constraints).toEqual(SPEC.constraints);
    expect(result.context).toEqual(SPEC.context);
    // A numerical constraint with categorical parameters is rejected server-side;
    // the UI must never silently remove the declared constraint to make it pass.
  });

  it("renames context in place without moving keyboard focus to another record", async () => {
    const user = userEvent.setup(); render(<Harness />);
    const key = screen.getAllByLabelText("Context key")[0];
    await user.clear(key); await user.type(key, "grade_revision");
    expect(key).toHaveFocus();
    expect(JSON.parse(screen.getByTestId("payload").textContent!).context).toEqual({ grade_revision: "A", process: "B" });
  });
});
