import { Badge } from "../../components/atoms/Badge";
import { EvidenceTypeLabel } from "../../components/atoms/EvidenceTypeLabel";

export type RunView = {
  id: string;
  kind: string;
  status: string;
  taskId?: string | null;
  queuedAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  error?: unknown;
  inputSummary?: unknown;
  resultSummary?: unknown;
};

export const TERMINAL_RUN_STATES = new Set([
  "succeeded", "failed", "timed_out", "cancelled", "interrupted", "blocked",
]);

export function runStateLabel(run: RunView): {
  label: string;
  tone: "info" | "success" | "warning" | "danger" | "neutral";
} {
  switch (run.status) {
    case "succeeded": return { label: "completed", tone: "success" };
    case "failed": return { label: run.resultSummary == null ? "failed — output unavailable" : "failed", tone: "danger" };
    case "timed_out": return { label: "timed out", tone: "danger" };
    case "interrupted": return { label: "interrupted", tone: "danger" };
    case "cancel_requested": return { label: "cancel requested…", tone: "warning" };
    case "awaiting_approval": return { label: "awaiting approval", tone: "warning" };
    case "blocked": return { label: "blocked", tone: "warning" };
    case "queued": case "running": return { label: run.status, tone: "info" };
    default: return { label: run.status, tone: "neutral" };
  }
}

export function record(value: unknown): Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "Not reported";
}

const RESOURCE_NAMES: Record<string, string> = {
  cpu_cores: "CPU cores", memory_bytes: "Memory", gpu_devices: "GPU devices",
  storage_bytes: "Storage", wall_seconds: "Time limit", concurrency: "Concurrent runs", group: "Resource group",
};

function resourceName(value: unknown) {
  return typeof value === "string" ? RESOURCE_NAMES[value] ?? value.replaceAll("_", " ") : "Local resources";
}

function resourceValue(value: unknown, dimension: unknown) {
  if (typeof value === "number" && typeof dimension === "string" && dimension.endsWith("_bytes")) return `${Number((value / 1024 ** 3).toFixed(2))} GiB`;
  return text(value);
}

function resourceReason(value: unknown): string {
  if (typeof value === "string") return value;
  const reason = record(value);
  const parts: string[] = [];
  if (reason.dimension) parts.push(resourceName(reason.dimension));
  if (reason.configuration) parts.push(`Configuration: ${text(reason.configuration)}`);
  if (reason.required != null) parts.push(`requires ${resourceValue(reason.required, reason.dimension)}`);
  if (reason.available != null) parts.push(`${resourceValue(reason.available, reason.dimension)} available`);
  if (reason.detail) parts.push(text(reason.detail));
  if (reason.reason) parts.push(text(reason.reason));
  return parts.join(" · ") || "The local resource requirement could not be met.";
}

export function RunTime({ value }: { value?: string | null }) {
  if (!value) return <>Not reported</>;
  const date = new Date(value);
  return <time dateTime={value}>{Number.isNaN(date.valueOf()) ? value : date.toLocaleString()}</time>;
}

const DESCRIPTORS: Record<string, { label: string; unit?: string }> = {
  mw: { label: "Molecular weight", unit: "g/mol" },
  exact_mw: { label: "Exact molecular weight", unit: "g/mol" },
  logp: { label: "LogP" },
  hbd: { label: "Hydrogen-bond donors" },
  hba: { label: "Hydrogen-bond acceptors" },
  tpsa: { label: "Topological polar surface area", unit: "Å²" },
  rotatable_bonds: { label: "Rotatable bonds" },
  num_atoms: { label: "Atoms" },
  num_heavy_atoms: { label: "Heavy atoms" },
  num_rings: { label: "Rings" },
  fraction_csp3: { label: "Fraction Csp³" },
};

/** Render authoritative results only. A failed/blocked run never
 * receives descriptor cards, even if it contains partial output. */
export function RunResult({ run, compact = false }: { run: RunView; compact?: boolean }) {
  const summary = record(run.resultSummary);
  const input = record(run.inputSummary);
  const structure = record(summary.structure);
  const engine = record(summary.engine);
  const descriptors = record(summary.descriptors);
  const error = record(run.error);
  const errorDetail = record(error.detail);
  const reasons = Array.isArray(errorDetail.reasons) ? errorDetail.reasons : [];
  const missing = Array.isArray(errorDetail.missing) ? errorDetail.missing : [];
  const state = runStateLabel(run);
  const isDescriptor = run.kind === "rdkit_descriptors";
  const completed = run.status === "succeeded";
  const rows = Object.entries(descriptors);
  const depiction = typeof structure.depiction_svg === "string" && /<(?:svg|\?xml)\b/.test(structure.depiction_svg) ? structure.depiction_svg : null;

  return (
    <div className={`cs-calculation-result${compact ? " cs-calculation-result--compact" : ""}`}>
      <div className="cs-calculation-result__status">
        <Badge tone={state.tone}>{state.label}</Badge>
        {isDescriptor && completed && <EvidenceTypeLabel kind="computed" />}
        {completed && isDescriptor && <span className="cs-field__hint">Molecular descriptors</span>}
      </div>
      {Object.keys(error).length > 0 && (
        <div className="cs-finding cs-finding--error" role="alert">
          <strong>{error.code === "PARSE_FAILED" ? "Check the molecular structure" : error.code === "SANITIZE_FAILED" ? "This structure could not be calculated" : "The calculation could not finish"}</strong><p>{text(error.message)}</p><small className="cs-error-code">{text(error.code)}</small>
        </div>
      )}
      {(reasons.length > 0 || missing.length > 0) && (
        <section aria-label="Local resource requirements">
          <h3>Why this run is blocked</h3>
          {reasons.length > 0 && <ul>{reasons.map((reason, index) => <li key={index}>{resourceReason(reason)}</li>)}</ul>}
          {missing.length > 0 && <p>Not observed on this device: {missing.map(resourceName).join(", ")}. Capacity must be known before this run can start.</p>}
          <p className="cs-field__hint">Review the resource requirements or the local capacity report before requesting another run.</p>
        </section>
      )}
      {isDescriptor && completed && rows.length > 0 ? (
        <>
          <div className="cs-molecule-summary">
          <figure className="cs-molecule-drawing">{depiction ? <img src={`data:image/svg+xml,${encodeURIComponent(depiction)}`} alt={`Molecular structure of ${text(structure.canonical_smiles)}`} /> : <code>{text(structure.canonical_smiles)}</code>}<figcaption>{depiction ? "2D structure · RDKit" : "Structure drawing unavailable"}</figcaption></figure>
          <dl className="cs-calculation-highlights">
            <div><dt>Molecular formula</dt><dd data-field="molecular-formula">{text(structure.formula)}</dd></div>
            <div><dt>Molecular weight</dt><dd data-field="molecular-weight">{text(descriptors.mw)} <small>g/mol</small></dd></div>
            <div><dt>Hydrogen-bond donors / acceptors</dt><dd>{text(descriptors.hbd)} / {text(descriptors.hba)}</dd></div>
          </dl>
          </div>
          {!compact && (
            <div className="cs-calculation-result__grid">
              <section aria-label="Computed descriptors">
                <h3>Computed descriptors</h3>
                <div className="cs-table-wrap" role="region" aria-label="Descriptor values" tabIndex={0}>
                  <table className="cs-table"><thead><tr><th scope="col">Property</th><th scope="col">Value</th><th scope="col">Unit</th></tr></thead>
                    <tbody>{rows.map(([key, value]) => <tr key={key}><th scope="row">{DESCRIPTORS[key]?.label ?? key}</th><td>{text(value)}</td><td>{DESCRIPTORS[key]?.unit ?? "Dimensionless"}</td></tr>)}</tbody>
                  </table>
                </div>
              </section>
              <aside className="cs-calculation-provenance" aria-label="Calculation provenance">
                <h3>Identity &amp; provenance</h3>
                <dl>
                  <div><dt>Canonical SMILES</dt><dd><code data-field="canonical-smiles">{text(structure.canonical_smiles)}</code></dd></div>
                  <div><dt>InChIKey</dt><dd><code data-field="inchi-key">{text(structure.inchi_key)}</code></dd></div>
                  <div><dt>Engine</dt><dd>{text(engine.id)} {text(engine.version)}</dd></div>
                  <div><dt>Method</dt><dd><code>{text(summary.method)}</code></dd></div>
                  <div><dt>Adapter</dt><dd><code>{text(summary.adapter_version)}</code></dd></div>
                  <div><dt>Evidence class</dt><dd>{text(summary.evidence_type)}</dd></div>
                </dl>
              </aside>
            </div>
          )}
          <p className="cs-calculation-note">Computed from the supplied molecular structure. These descriptors are not laboratory measurements or a scientific validation of a research hypothesis.</p>
        </>
      ) : completed && run.resultSummary != null ? (
        <details><summary>Result summary</summary><pre className="cs-json">{JSON.stringify(run.resultSummary, null, 2)}</pre></details>
      ) : (
        <p className="cs-field__hint">{TERMINAL_RUN_STATES.has(run.status) ? "No completed calculation result is available." : "The run is in progress. Results will appear after completion."}</p>
      )}
      {!compact && (
        <>
          {Object.keys(input).length > 0 && <section aria-label="Calculation input"><h3>Calculation input</h3><dl className="cs-calculation-input"><div><dt>Submitted SMILES</dt><dd><code>{text(input.smiles ?? record(summary.input).smiles)}</code></dd></div>{input.inputDigest != null && <div><dt>Input digest</dt><dd><code>{text(input.inputDigest)}</code></dd></div>}</dl></section>}
          <dl className="cs-calculation-times"><div><dt>Queued</dt><dd><RunTime value={run.queuedAt} /></dd></div><div><dt>Started</dt><dd><RunTime value={run.startedAt} /></dd></div><div><dt>Finished</dt><dd><RunTime value={run.finishedAt} /></dd></div></dl>
          <details className="cs-calculation-raw"><summary>Technical details</summary><pre className="cs-json">{JSON.stringify({ input: run.inputSummary ?? null, result: run.resultSummary ?? null, error: run.error ?? null }, null, 2)}</pre></details>
        </>
      )}
    </div>
  );
}
