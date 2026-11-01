import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActualsCaptureForm, ContractMetricForm, HistoricalRecordForm } from "./LabCaptureForms";

describe("explicit lab capture", () => {
  it("starts actuals, citations and comparison targets blank and cannot submit examples", () => {
    const save = vi.fn();
    render(<><ActualsCaptureForm pending={false} onSubmit={save} /><HistoricalRecordForm pending={false} onSubmit={save} /><ContractMetricForm onCompare={save} /></>);
    fireEvent.click(screen.getByText("record actuals / deviations"));
    fireEvent.click(screen.getByText("import historical record (never retrospectively approved)"));
    expect(screen.getByLabelText("Actual process")).toHaveValue("");
    expect(screen.getByLabelText("Historical source")).toHaveValue("");
    expect(screen.getByLabelText("Comparison metric name")).toHaveValue("");
    expect(screen.getByLabelText("Comparison comparator")).toHaveValue("");
    expect(screen.getByLabelText("Comparison bound")).toHaveValue("");
    expect(screen.getByLabelText("Comparison unit")).toHaveValue("");
    for (const name of ["record actuals", "import historical record", "compare"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toBeDisabled(); fireEvent.click(button);
    }
    expect(save).not.toHaveBeenCalled();
    expect(screen.queryByDisplayValue("as planned")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("lab notebook p.41")).not.toBeInTheDocument();
  });

  it("records the entered process exactly without inventing materials or deviations", () => {
    const save = vi.fn(); render(<ActualsCaptureForm pending={false} onSubmit={save} />);
    fireEvent.click(screen.getByText("record actuals / deviations"));
    const process = "  Mixed by hand for 2 minutes.\nStopped when the instrument failed.  ";
    fireEvent.change(screen.getByLabelText("Actual process"), { target: { value: process } });
    fireEvent.click(screen.getByRole("button", { name: "record actuals" }));
    expect(save).toHaveBeenCalledWith({ actual: { process } });
  });

  it("preserves an explicitly entered zero material amount with its lot and unit", () => {
    const save = vi.fn(); render(<ActualsCaptureForm pending={false} onSubmit={save} />);
    fireEvent.click(screen.getByText("record actuals / deviations"));
    fireEvent.click(screen.getByRole("button", { name: "Add materials used" }));
    const record = screen.getByRole("button", { name: "record actuals" });
    expect(record).toBeDisabled();
    for (const [label, value] of [["Material name", "Control material"], ["Material lot", "LOT-0"], ["Material amount", "0"], ["Material unit", "g"]]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(record);
    expect(save).toHaveBeenCalledWith({ actual: { materials: [{ material: "Control material", lot: "LOT-0", amount: "0", unit: "g" }] } });
  });

  it("requires an actual source even when historical notes are provided", () => {
    const save = vi.fn(); render(<HistoricalRecordForm pending={false} onSubmit={save} />);
    fireEvent.click(screen.getByText("import historical record (never retrospectively approved)"));
    fireEvent.change(screen.getByLabelText("Historical notes (optional)"), { target: { value: "Instrument unavailable\nNo reading recorded" } });
    const button = screen.getByRole("button", { name: "import historical record" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Historical source"), { target: { value: " Notebook X, page 7 " } });
    fireEvent.click(button);
    expect(save).toHaveBeenCalledWith({ source: " Notebook X, page 7 ", notes: "Instrument unavailable\nNo reading recorded" });
  });

  it("treats zero as a comparison bound and preserves decimal precision in the existing target wire format", () => {
    const compare = vi.fn(); render(<ContractMetricForm onCompare={compare} />);
    fireEvent.change(screen.getByLabelText("Comparison metric name"), { target: { value: "Index" } });
    fireEvent.change(screen.getByLabelText("Comparison comparator"), { target: { value: ">=" } });
    fireEvent.change(screen.getByLabelText("Comparison bound"), { target: { value: "0" } });
    const button = screen.getByRole("button", { name: "compare" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Comparison unit"), { target: { value: "dimensionless" } });
    fireEvent.click(button);
    expect(compare).toHaveBeenLastCalledWith({ name: "Index", target: ">= 0 dimensionless" });
    fireEvent.change(screen.getByLabelText("Comparison bound"), { target: { value: "0.000000000000000001" } });
    fireEvent.click(button);
    expect(compare).toHaveBeenLastCalledWith({ name: "Index", target: ">= 0.000000000000000001 dimensionless" });
  });

  it("requires an explicit valid advanced payload and never mixes it with hidden structured input", () => {
    const save = vi.fn(); render(<ActualsCaptureForm pending={false} onSubmit={save} />);
    fireEvent.click(screen.getByText("record actuals / deviations"));
    fireEvent.change(screen.getByLabelText("Actual process"), { target: { value: "Structured process" } });
    fireEvent.click(screen.getByText("Advanced actuals payload"));
    fireEvent.click(screen.getByLabelText("Use exact actuals payload"));
    expect(screen.getByLabelText("Actual process")).toBeDisabled();
    const button = screen.getByRole("button", { name: "record actuals" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("actual materials and process (JSON)"), { target: { value: "{}" } });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("actual materials and process (JSON)"), { target: { value: '{"temperature":0,"method":"Actual method"}' } });
    fireEvent.click(button);
    expect(save).toHaveBeenCalledWith({ actual: { temperature: 0, method: "Actual method" } });
  });
});
