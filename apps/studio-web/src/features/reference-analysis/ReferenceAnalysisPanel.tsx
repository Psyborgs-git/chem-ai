import { useRef, useState } from "react";
import { useFragment, useMutation } from "react-relay";

import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { EmptyState } from "../../components/states/states";
import {
  AnalyticalCompareMutation,
  AnalyticalIngestMutation,
  ReferenceAnalysisFragment,
} from "./operations";
import type { ReferenceAnalysisPanel_task$key } from "../../__generated__/ReferenceAnalysisPanel_task.graphql";
import type { referenceAnalysisIngestMutation } from "../../__generated__/referenceAnalysisIngestMutation.graphql";
import type { referenceAnalysisCompareMutation } from "../../__generated__/referenceAnalysisCompareMutation.graphql";

export type SeriesManifest = {
  seriesId: string;
  taskId: string;
  label: string;
  method: string;
  sampleId: string | null;
  sample: { label: string; sample_id?: string | null; preparation?: string | null };
  instrument: Record<string, string | null>;
  calibration: Record<string, string | null> | null;
  sourceFormat: string | null;
  interpretationState: string;
  rawArtifactId: string;
  processedArtifactId: string | null;
  transform: {
    parser_version?: string;
    preprocessing?: ReadonlyArray<{ kind: string; version: string; parameters: Record<string, unknown> }>;
  } | null;
  detail: Record<string, unknown>;
};

export type ComparisonManifest = {
  taskId: string;
  leftSeriesId: string;
  rightSeriesId: string;
  resultArtifactId: string;
  similarity: {
    algorithm: string;
    algorithm_version: string;
    value: number;
    scope: { x_unit: string; range_min: number; range_max: number; aligned_points: number };
    interpretation_limits: ReadonlyArray<string>;
    adapter_version: string;
    scientific_status: string;
  };
  transform: unknown;
};

const METHODS = ["infrared", "uv_vis", "raman", "nmr_1h"] as const;

export function SeriesRow({ manifest }: { manifest: SeriesManifest }) {
  const unsupported = manifest.interpretationState !== "processed";
  return (
    <tr>
      <td className="cs-table__identity">{manifest.label}</td>
      <td>{manifest.method}</td>
      <td>{manifest.sourceFormat ?? "unsupported format"}</td>
      <td>
        {unsupported
          ? <Badge tone="warning">unsupported</Badge>
          : <Badge tone="neutral">processed</Badge>}
        {unsupported && (
          <p role="note">raw export retained with provenance; no interpretation is available and none was guessed.</p>
        )}
      </td>
      <td>
        <small>raw {manifest.rawArtifactId.slice(0, 8)}… → processed {manifest.processedArtifactId ? `${manifest.processedArtifactId.slice(0, 8)}…` : "none"}</small>
        {manifest.transform && (
          <details>
            <summary>transform record</summary>
            <pre>{JSON.stringify(manifest.transform, null, 2)}</pre>
          </details>
        )}
      </td>
      <td>
        <small>
          sample {manifest.sample.label}
          {manifest.instrument.vendor ? ` · ${manifest.instrument.vendor}` : ""}
          {manifest.instrument.model ? ` ${manifest.instrument.model}` : ""}
          {manifest.calibration?.reference ? ` · cal. ${manifest.calibration.reference}` : ""}
        </small>
      </td>
    </tr>
  );
}

export function ComparisonCard({ manifest, labels }: { manifest: ComparisonManifest; labels: Map<string, string> }) {
  const s = manifest.similarity;
  const left = labels.get(manifest.leftSeriesId) ?? manifest.leftSeriesId.slice(0, 8);
  const right = labels.get(manifest.rightSeriesId) ?? manifest.rightSeriesId.slice(0, 8);
  return (
    <section aria-label={`comparison ${left} vs ${right}`}>
      <h4>
        {left} ↔ {right} · {s.algorithm} = {s.value.toFixed(4)}{" "}
        <Badge tone="warning">{s.scientific_status}</Badge>
      </h4>
      <p>
        scoped to {s.scope.x_unit} {s.scope.range_min.toFixed(2)}–{s.scope.range_max.toFixed(2)}
        {" · "}{s.scope.aligned_points} aligned points · {s.algorithm_version} · {s.adapter_version}
      </p>
      <ul aria-label="interpretation limits">
        {s.interpretation_limits.map((l) => <li key={l}>{l}</li>)}
      </ul>
      <details><summary>transform record</summary><pre>{JSON.stringify(manifest.transform, null, 2)}</pre></details>
    </section>
  );
}

export function ReferenceAnalysisPanel({ taskRef }: { taskRef: ReferenceAnalysisPanel_task$key }) {
  const task = useFragment(ReferenceAnalysisFragment, taskRef);
  const [artifactId, setArtifactId] = useState("");
  const [spec, setSpec] = useState("");
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [algorithm, setAlgorithm] = useState<string>("cosine");
  const [rangeMin, setRangeMin] = useState("");
  const [rangeMax, setRangeMax] = useState("");
  const [message, setMessage] = useState("");
  const [ingest, ingesting] = useMutation<referenceAnalysisIngestMutation>(AnalyticalIngestMutation);
  const [compare, comparing] = useMutation<referenceAnalysisCompareMutation>(AnalyticalCompareMutation);
  const busy = ingesting || comparing;
  const ingestKey = useRef({ payload: "", key: "" });
  const compareKey = useRef({ payload: "", key: "" });

  const series = task.analyticalSeries.map((s) => s.manifest as SeriesManifest);
  const labels = new Map(series.map((s) => [s.seriesId, s.label]));
  const processed = task.analyticalSeries.filter((s) => s.interpretationState === "processed");

  function retryKey(ref: { current: { payload: string; key: string } }, payload: unknown) {
    const serialized = JSON.stringify(payload);
    if (ref.current.payload !== serialized) {
      ref.current = { payload: serialized, key: crypto.randomUUID() };
    }
    return ref.current.key;
  }

  function submitIngest() {
    let parsed: unknown;
    try {
      parsed = JSON.parse(spec);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
    } catch {
      setMessage("Provide an ingest spec JSON object (method, units, sample, instrument/context). Nothing is invented.");
      return;
    }
    if (!/^[0-9a-fA-F-]{36}$/.test(artifactId.trim())) {
      setMessage("Provide the raw export artifact id (uuid). The artifact must already be committed to the vault.");
      return;
    }
    setMessage("");
    const input = { taskId: task.id, rawArtifactId: artifactId.trim(), spec: parsed };
    ingest({
      variables: { input: { ...input, idempotencyKey: retryKey(ingestKey, input) } },
      onCompleted: (data) =>
        setMessage(
          data.analytical.ingest.errors.map((e) => `${e.code}: ${e.message}`).join("; ") ||
            "Series recorded. Unsupported formats are stored raw and marked 'unsupported' — never parsed by guesswork."
        ),
      onError: () =>
        setMessage("Request outcome unknown. Retry unchanged inputs with the same key, or reload to inspect the saved series."),
    });
  }

  function submitCompare() {
    if (!leftId || !rightId) { setMessage("Select two processed series — comparisons only run on processed values."); return; }
    if (leftId === rightId) { setMessage("Choose two different series."); return; }
    const min = rangeMin.trim() === "" ? null : Number(rangeMin);
    const max = rangeMax.trim() === "" ? null : Number(rangeMax);
    if ((min !== null && !Number.isFinite(min)) || (max !== null && !Number.isFinite(max))) {
      setMessage("Range bounds must be numeric in the trace's x unit.");
      return;
    }
    if (min !== null && max !== null && !(min < max)) {
      setMessage("Range minimum must be below range maximum.");
      return;
    }
    setMessage("");
    const specObject = { similarity: { algorithm, range_min: min, range_max: max } };
    const input = { taskId: task.id, leftSeriesId: leftId, rightSeriesId: rightId, spec: specObject };
    compare({
      variables: { input: { ...input, idempotencyKey: retryKey(compareKey, input) } },
      onCompleted: (data) =>
        setMessage(
          data.analytical.compare.errors.map((e) => `${e.code}: ${e.message}`).join("; ") ||
            "Comparison recorded. The similarity value is scoped to its algorithm and range — it is not composition evidence."
        ),
      onError: () =>
        setMessage("Request outcome unknown. Retry unchanged inputs with the same key, or reload to inspect the saved comparison."),
    });
  }

  return (
    <div>
      <p>
        Reference comparison of analytical exports (§16.5). Processing is separate from
        interpretation and identity: every value carries its transform version and a
        scoped similarity is never evidence of identical composition, recipe, or structure.
      </p>
      <p>
        Supported export readers: <Badge tone="info">jcamp-dx</Badge> <Badge tone="info">csv-xy</Badge>
        {" "}— anything else ingests as raw-only with interpretation <Badge tone="warning">unsupported</Badge>.
      </p>

      <h4>Ingest a raw export</h4>
      <TextField label="Raw export artifact id (uuid)" value={artifactId} onChange={(e) => setArtifactId(e.target.value)} />
      <label>
        Ingest spec JSON (method ∈ {METHODS.join("/")})
        <textarea aria-label="Ingest spec JSON" rows={8} value={spec} onChange={(e) => setSpec(e.target.value)} />
      </label>
      <Button onClick={submitIngest} disabled={busy || !spec.trim() || !artifactId.trim()}>Ingest series</Button>

      <h4>Series ({task.analyticalSeries.length})</h4>
      {task.analyticalSeries.length === 0 && (
        <EmptyState title="No analytical series. Commit an instrument export to the vault, then ingest it here with its method/context." />
      )}
      {task.analyticalSeries.length > 0 && (
        <div
          className="cs-table-wrap"
          role="region"
          aria-label="analytical series"
          tabIndex={0}
        >
          <table className="cs-table">
            <caption>raw↔processed lineage, transform versions, and capability state per series</caption>
            <thead>
              <tr><th scope="col" className="cs-table__identity">Label</th><th scope="col">Method</th><th scope="col">Format</th><th scope="col">Interpretation</th><th scope="col">Lineage / transform</th><th scope="col">Sample / instrument</th></tr>
            </thead>
            <tbody>
              {series.map((s) => <SeriesRow key={s.seriesId} manifest={s} />)}
            </tbody>
          </table>
        </div>
      )}

      <h4>Compare two processed series</h4>
      <label>
        Left series
        <select aria-label="Left series" value={leftId} onChange={(e) => setLeftId(e.target.value)}>
          <option value="">—</option>
          {processed.map((s) => <option key={s.id} value={s.id}>{s.label} ({s.method})</option>)}
        </select>
      </label>
      <label>
        Right series
        <select aria-label="Right series" value={rightId} onChange={(e) => setRightId(e.target.value)}>
          <option value="">—</option>
          {processed.map((s) => <option key={s.id} value={s.id}>{s.label} ({s.method})</option>)}
        </select>
      </label>
      <label>
        Algorithm
        <select aria-label="Algorithm" value={algorithm} onChange={(e) => setAlgorithm(e.target.value)}>
          <option value="cosine">cosine-similarity/v1</option>
          <option value="pearson">pearson-correlation/v1</option>
        </select>
      </label>
      <TextField label="Range min (x unit, optional)" inputMode="decimal" value={rangeMin} onChange={(e) => setRangeMin(e.target.value)} />
      <TextField label="Range max (x unit, optional)" inputMode="decimal" value={rangeMax} onChange={(e) => setRangeMax(e.target.value)} />
      <Button onClick={submitCompare} disabled={busy || processed.length < 2}>Compute scoped similarity</Button>
      {processed.length < 2 && <p role="note">at least two processed series are required for a comparison.</p>}
      {message && <p role="status">{message}</p>}

      <h4>Comparisons ({task.analyticalComparisons.length})</h4>
      {task.analyticalComparisons.map((c) => (
        <ComparisonCard key={c.id} manifest={c.manifest as ComparisonManifest} labels={labels} />
      ))}
    </div>
  );
}
