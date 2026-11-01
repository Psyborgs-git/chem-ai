import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { StructuredRows } from "./StructuredRows";

function Harness({ initial = "" }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return <><StructuredRows label="Thresholds" value={value} onChange={setValue}
    newRow={{ metric: "", value: null, coefficients: [] }} fields={[
      { key: "metric", label: "Metric" }, { key: "value", label: "Threshold", kind: "number" },
      { key: "coefficients", label: "Coefficients", kind: "numbers" },
    ]} /><output data-testid="payload">{value}</output></>;
}

describe("Structured scientific row editing", () => {
  it("keeps an unspecified threshold unknown while editing other fields", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Add thresholds" }));
    await user.type(screen.getByLabelText("Metric"), "purity");
    expect(screen.getByLabelText("Threshold")).toHaveValue(null);
    expect(JSON.parse(screen.getByTestId("payload").textContent!)[0]).toEqual({ metric: "purity", value: null, coefficients: [] });
  });

  it("allows normal comma-separated typing and preserves decimal precision", async () => {
    const user = userEvent.setup();
    render(<Harness initial='[{"metric":"m","value":null,"coefficients":[]}]' />);
    await user.type(screen.getByLabelText("Coefficients"), "0.125, 0.875");
    expect(JSON.parse(screen.getByTestId("payload").textContent!)[0].coefficients).toEqual(["0.125", "0.875"]);
  });

  it("preserves unedited context and refuses an invalid advanced payload", async () => {
    const user = userEvent.setup();
    render(<Harness initial='[{"metric":"m","value":null,"coefficients":[],"context":{"method":"reviewed-v1"}}]' />);
    await user.clear(screen.getByLabelText("Metric"));
    await user.type(screen.getByLabelText("Metric"), "density");
    expect(JSON.parse(screen.getByTestId("payload").textContent!)[0].context).toEqual({ method: "reviewed-v1" });
    await user.click(screen.getByText("Advanced: edit thresholds payload"));
    fireEvent.change(screen.getByLabelText("Thresholds (JSON array)"), { target: { value: "{}" } });
    expect(screen.getByRole("alert")).toHaveTextContent("JSON array of records");
    expect(screen.queryByLabelText("Metric")).not.toBeInTheDocument();
  });
});
