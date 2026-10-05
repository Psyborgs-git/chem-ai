import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";

vi.mock("react-relay", () => ({
  graphql: () => ({}),
  useFragment: () => ({ id: "task-fixture", analyticalSeries: [], analyticalComparisons: [] }),
  useMutation: () => [vi.fn(), false],
}));

import {
  ComparisonCard,
  ReferenceAnalysisPanel,
  SeriesRow,
  type ComparisonManifest,
  type SeriesManifest,
} from "./ReferenceAnalysisPanel";
import type { ReferenceAnalysisPanel_task$key } from "../../__generated__/ReferenceAnalysisPanel_task.graphql";

const unsupportedSeries: SeriesManifest = {
  seriesId: "s-1",
  taskId: "t-1",
  label: "vendor export A",
  method: "infrared",
  sampleId: null,
  sample: { label: "film A" },
  instrument: { vendor: "ACME", model: "SPC-9" },
  calibration: null,
  sourceFormat: null,
  interpretationState: "unsupported",
  rawArtifactId: "a1b2c3d4-0000-0000-0000-000000000000",
  processedArtifactId: null,
  transform: null,
  detail: { reason: "export format not supported" },
};

const comparison: ComparisonManifest = {
  taskId: "t-1",
  leftSeriesId: "s-1",
  rightSeriesId: "s-2",
  resultArtifactId: "r-1",
  similarity: {
    algorithm: "cosine",
    algorithm_version: "cosine-similarity/v1",
    value: 0.9965,
    scope: { x_unit: "1/CM", range_min: 400.0, range_max: 3600.0, aligned_points: 2048 },
    interpretation_limits: [
      "similarity is scoped to the aligned x range and the selected algorithm only",
      "a matching similarity value is not evidence of identical composition, recipe, or molecular identity",
    ],
    adapter_version: "analytics-adapter/v1",
    scientific_status: "not_composition_evidence",
  },
  transform: { alignment: { kind: "resample_linear", version: "resample-linear/v1" } },
};

describe("reference analysis capability states (AT-0703-2/3)", () => {
  it("marks an unsupported series with the blocked label and no fabricated interpretation", () => {
    render(<table><tbody><SeriesRow manifest={unsupportedSeries} /></tbody></table>);
    expect(screen.getByText("unsupported")).toBeInTheDocument();
    expect(screen.getByText(/no interpretation is available and none was guessed/)).toBeInTheDocument();
    expect(screen.queryByText(/processed values/)).not.toBeInTheDocument();
  });

  it("shows scoped similarity with its limits and no composition-identity claim", () => {
    render(<ComparisonCard manifest={comparison} labels={new Map([["s-1", "film A"], ["s-2", "film B"]])} />);
    expect(screen.getByText(/cosine = 0\.9965/)).toBeInTheDocument();
    expect(screen.getByText("not_composition_evidence")).toBeInTheDocument();
    expect(screen.getByText(/400\.00–3600\.00/)).toBeInTheDocument();
    expect(screen.getByText(/2048 aligned points/)).toBeInTheDocument();
    expect(screen.getByText(/not evidence of identical composition/)).toBeInTheDocument();
    expect(screen.queryByText(/identity confirmed|complete recipe/i)).not.toBeInTheDocument();
  });

  it("rejects an invalid ingest spec instead of inventing context", async () => {
    const user = userEvent.setup();
    render(<ReferenceAnalysisPanel taskRef={{} as ReferenceAnalysisPanel_task$key} />);
    expect(screen.getByText(/No analytical series/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Raw export artifact id (uuid)"), "a1b2c3d4-0000-0000-0000-000000000000");
    await user.type(screen.getByLabelText("Ingest spec JSON"), "not JSON");
    await user.click(screen.getByRole("button", { name: "Ingest series" }));
    expect(screen.getByText(/Nothing is invented/)).toBeInTheDocument();
  });
});
