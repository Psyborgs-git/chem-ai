import { useState } from "react";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { StructuredRows } from "../../../components/molecules/StructuredRows";

type Json = Record<string, unknown>;
export type ActualsCapture = { actual?: Json; deviations?: Json[]; observations?: string };

function object(value: unknown): value is Json {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function entered(value: unknown): boolean {
  if (typeof value === "string") return value.trim().length > 0;
  if (typeof value === "number" || typeof value === "boolean") return true;
  if (Array.isArray(value)) return value.some(entered);
  return object(value) && Object.values(value).some(entered);
}
function rows(text: string): Json[] {
  const value: unknown = text.trim() ? JSON.parse(text) : [];
  if (!Array.isArray(value) || !value.every(object)) throw new Error("Use an array of records.");
  return value;
}
function ErrorNotice({ error }: { error: string | null }) {
  return error ? <p role="alert" className="cs-field__error">{error}</p> : null;
}

/** Blank capture forms cannot turn illustrative defaults into scientific records. */
export function ActualsCaptureForm({ pending, onSubmit }: {
  pending: boolean; onSubmit: (capture: ActualsCapture) => void;
}) {
  const [process, setProcess] = useState("");
  const [materials, setMaterials] = useState("");
  const [deviations, setDeviations] = useState("");
  const [observations, setObservations] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [actualText, setActualText] = useState("");
  const [deviationsText, setDeviationsText] = useState("");
  const [error, setError] = useState<string | null>(null);

  function capture(): ActualsCapture {
    let actual: Json | undefined;
    let recordedDeviations: Json[] | undefined;
    if (advanced) {
      if (actualText.trim()) {
        const parsed: unknown = JSON.parse(actualText);
        if (!object(parsed)) throw new Error("Actual materials and process must be a JSON object.");
        if (entered(parsed)) actual = parsed;
      }
      if (deviationsText.trim()) recordedDeviations = rows(deviationsText);
    } else {
      const materialRows = rows(materials).filter(entered);
      if (materialRows.some((row) => !entered(row.material) && !entered(row.lot))) throw new Error("Identify each entered material by its name or lot.");
      if (materialRows.some((row) => entered(row.amount) && !entered(row.unit))) throw new Error("Record a unit beside each material amount.");
      const actualFields = { ...(process.trim() ? { process } : {}), ...(materialRows.length ? { materials: materialRows } : {}) };
      if (entered(actualFields)) actual = actualFields;
      const deviationRows = rows(deviations).filter(entered);
      if (deviationRows.some((row) => !entered(row.description))) throw new Error("Describe each entered deviation.");
      if (deviationRows.length) recordedDeviations = deviationRows;
    }
    if (!entered(actual) && !entered(recordedDeviations) && !observations.trim()) throw new Error("Enter actual process, materials, a deviation or an observation before recording.");
    return { ...(actual ? { actual } : {}), ...(recordedDeviations ? { deviations: recordedDeviations } : {}), ...(observations.trim() ? { observations } : {}) };
  }
  let ready = false;
  try { capture(); ready = true; } catch { /* Invalid drafts remain editable. */ }

  return <details data-field="actuals-form">
    <summary>record actuals / deviations</summary>
    <p className="cs-field__hint">Record what actually happened. Blank fields make no claim about the planned process or the materials used.</p>
    <fieldset disabled={advanced || pending}><legend>Actual process & materials</legend>
      <label className="cs-field"><span className="cs-field__label">Actual process</span><textarea className="cs-input" rows={3} value={process} onChange={(e) => setProcess(e.target.value)} /></label>
      <StructuredRows label="Materials used" value={materials} onChange={setMaterials} advanced={false}
        newRow={{ material: "", lot: "", amount: "", unit: "" }} fields={[
          { key: "material", label: "Material name" }, { key: "lot", label: "Material lot" },
          { key: "amount", label: "Material amount", hint: "As recorded; an intentional zero stays zero" }, { key: "unit", label: "Material unit" },
        ]} />
      <StructuredRows label="Deviations" value={deviations} onChange={setDeviations} advanced={false}
        newRow={{ description: "", impact: "" }} fields={[
          { key: "description", label: "Deviation description", kind: "text" }, { key: "impact", label: "Deviation impact (optional)", kind: "text" },
        ]} />
    </fieldset>
    <label className="cs-field"><span className="cs-field__label">observations</span><textarea className="cs-input" rows={3} value={observations} onChange={(e) => setObservations(e.target.value)} disabled={pending} /></label>
    <details className="cs-technical"><summary>Advanced actuals payload</summary>
      <label className="cs-checkbox"><input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} disabled={pending} />Use exact actuals payload</label>
      <p className="cs-field__hint">When selected, these payloads replace the structured process/material and deviation fields. Observations remain separate.</p>
      <label className="cs-field"><span className="cs-field__label">actual materials and process (JSON)</span><textarea className="cs-input cs-mono" rows={4} value={actualText} onChange={(e) => setActualText(e.target.value)} disabled={!advanced || pending} /></label>
      <label className="cs-field"><span className="cs-field__label">deviations (JSON list)</span><textarea className="cs-input cs-mono" rows={3} value={deviationsText} onChange={(e) => setDeviationsText(e.target.value)} disabled={!advanced || pending} /></label>
    </details>
    <ErrorNotice error={error} />
    <Button disabled={pending || !ready} onClick={() => { if (pending) return; try { const value = capture(); setError(null); onSubmit(value); } catch (e) { setError(e instanceof Error ? e.message : "Check the actuals fields."); } }}>record actuals</Button>
  </details>;
}

export function HistoricalRecordForm({ pending, onSubmit }: { pending: boolean; onSubmit: (payload: Json) => void }) {
  const [source, setSource] = useState("");
  const [notes, setNotes] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  function payload(): Json {
    const value: unknown = advanced ? JSON.parse(text) : { source, ...(notes.trim() ? { notes } : {}) };
    if (!object(value) || typeof value.source !== "string" || !value.source.trim()) throw new Error("Record the historical source before importing.");
    return value;
  }
  let ready = false;
  try { payload(); ready = true; } catch { /* No source is invented for blank drafts. */ }
  return <details data-field="historical-import">
    <summary>import historical record (never retrospectively approved)</summary>
    <p className="cs-field__hint">Enter the actual source citation. This record carries no retrospective plan approval.</p>
    <fieldset disabled={advanced || pending}><legend>Historical record</legend>
      <TextField label="Historical source" hint="The source and locator you actually reviewed" value={source} onChange={(e) => setSource(e.target.value)} required />
      <label className="cs-field"><span className="cs-field__label">Historical notes (optional)</span><textarea className="cs-input" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
    </fieldset>
    <details className="cs-technical"><summary>Advanced historical payload</summary>
      <label className="cs-checkbox"><input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} disabled={pending} />Use exact historical payload</label>
      <p className="cs-field__hint">The exact object must include the actual source citation in its source field.</p>
      <label className="cs-field"><span className="cs-field__label">historical record payload (JSON)</span><textarea className="cs-input cs-mono" rows={5} value={text} onChange={(e) => setText(e.target.value)} disabled={!advanced || pending} /></label>
    </details>
    <ErrorNotice error={error} />
    <Button disabled={pending || !ready} onClick={() => { if (pending) return; try { const value = payload(); setError(null); onSubmit(value); } catch (e) { setError(e instanceof Error ? e.message : "Check the source."); } }}>import historical record</Button>
  </details>;
}

const NUMBER = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
const COMPARATORS = [">=", "<=", ">", "<", "="];

export function ContractMetricForm({ onCompare }: { onCompare: (metric: Json) => void }) {
  const [name, setName] = useState("");
  const [operator, setOperator] = useState("");
  const [bound, setBound] = useState("");
  const [unit, setUnit] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  function metric(): Json {
    if (advanced) {
      const parsed: unknown = JSON.parse(text);
      if (!object(parsed) || typeof parsed.name !== "string" || !parsed.name.trim() || typeof parsed.target !== "string" || !parsed.target.trim()) throw new Error("Provide a metric name and target in the exact metric object.");
      return parsed;
    }
    if (!name.trim() || !COMPARATORS.includes(operator) || !NUMBER.test(bound.trim()) || !unit.trim()) throw new Error("Enter the metric name, comparator, numeric bound and unit.");
    return { name, target: `${operator} ${bound.trim()} ${unit.trim()}` };
  }
  let ready = false;
  try { metric(); ready = true; } catch { /* Blank is unknown; zero is a valid bound. */ }
  return <div className="cs-page-stack">
    <fieldset className="cs-form-grid" disabled={advanced}><legend>Comparison target</legend>
      <TextField label="Comparison metric name" value={name} onChange={(e) => setName(e.target.value)} />
      <label className="cs-field"><span className="cs-field__label">Comparison comparator</span><select className="cs-select" value={operator} onChange={(e) => setOperator(e.target.value)}><option value="">Select a comparator…</option>{COMPARATORS.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      <TextField label="Comparison bound" inputMode="decimal" value={bound} onChange={(e) => setBound(e.target.value)} />
      <TextField label="Comparison unit" hint="Record dimensionless explicitly when applicable" value={unit} onChange={(e) => setUnit(e.target.value)} />
    </fieldset>
    <details className="cs-technical"><summary>Advanced comparison target</summary>
      <label className="cs-checkbox"><input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} />Use exact comparison metric</label>
      <label className="cs-field"><span className="cs-field__label">contract metric (JSON)</span><textarea className="cs-input cs-mono" rows={4} value={text} onChange={(e) => setText(e.target.value)} disabled={!advanced} /></label>
    </details>
    <ErrorNotice error={error} />
    <Button disabled={!ready} onClick={() => { try { const value = metric(); setError(null); onCompare(value); } catch (e) { setError(e instanceof Error ? e.message : "Check the comparison target."); } }}>compare</Button>
  </div>;
}
