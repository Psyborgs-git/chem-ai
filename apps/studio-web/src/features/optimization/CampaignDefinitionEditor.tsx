import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { CommaListField, StructuredRows } from "../../components/molecules/StructuredRows";

type RecordValue = Record<string, unknown>;
const initial = (): RecordValue => ({ parameters: [], target: { name: "", mode: "maximize", unit: "", method: "" }, constraints: [], context: {}, seed: 0, recommender: "two_phase", switch_after: 3 });

/** Maps the supported campaign contract to controls; advanced payloads retain all fields. */
export function CampaignDefinitionEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  let spec: RecordValue = initial();
  let valid = true;
  try {
    if (value.trim()) {
      const parsed: unknown = JSON.parse(value);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) valid = false;
      else spec = parsed as RecordValue;
    }
  } catch { valid = false; }
  const write = (next: RecordValue) => onChange(JSON.stringify(next, null, 2));
  const update = (field: string, next: unknown) => write({ ...spec, [field]: next });
  const target = (spec.target ?? {}) as RecordValue;
  const context = (spec.context ?? {}) as Record<string, string>;
  const parameters = (Array.isArray(spec.parameters) ? spec.parameters : []) as RecordValue[];
  const changeParameter = (index: number, next: RecordValue) => update("parameters", parameters.map((p, i) => i === index ? next : p));
  return <section className="cs-campaign-editor" aria-label="Campaign definition">
    <h3>Define the approved search space</h3>
    <p className="cs-field__hint">A frozen campaign fixes the parameters, target, method, constraints and context. Its suggestions never approve an experiment.</p>
    {!valid ? <p role="alert" className="cs-field__error">Correct the advanced campaign JSON to use the structured editor.</p> : <>
      <fieldset><legend>Parameters</legend>
        {parameters.map((parameter, index) => <section key={index} className="cs-rows-editor__row">
          <header className="cs-list__row"><strong>Parameter {index + 1}</strong><Button variant="ghost" onClick={() => update("parameters", parameters.filter((_, i) => i !== index))}>Remove parameter</Button></header>
          <div className="cs-form-grid">
            <TextField label="Parameter name" value={String(parameter.name ?? "")} onChange={(e) => changeParameter(index, { ...parameter, name: e.target.value })} />
            <label className="cs-field"><span className="cs-field__label">Parameter type</span><select className="cs-select" value={String(parameter.kind ?? "discrete")} onChange={(e) => {
              const next = { name: parameter.name, unit: parameter.unit, kind: e.target.value, [e.target.value === "continuous" ? "bounds" : e.target.value === "categorical" ? "categories" : "values"]: [] };
              changeParameter(index, next);
            }}>{["continuous", "discrete", "categorical"].map((kind) => <option key={kind}>{kind}</option>)}</select></label>
            <TextField label="Parameter unit" value={String(parameter.unit ?? "")} onChange={(e) => changeParameter(index, { ...parameter, unit: e.target.value })} />
            {parameter.kind === "continuous" ? <>
              <TextField label="Lower bound" inputMode="decimal" value={String((parameter.bounds as string[] | undefined)?.[0] ?? "")} onChange={(e) => changeParameter(index, { ...parameter, bounds: [e.target.value, (parameter.bounds as string[] | undefined)?.[1] ?? ""] })} />
              <TextField label="Upper bound" inputMode="decimal" value={String((parameter.bounds as string[] | undefined)?.[1] ?? "")} onChange={(e) => changeParameter(index, { ...parameter, bounds: [(parameter.bounds as string[] | undefined)?.[0] ?? "", e.target.value] })} />
            </> : <CommaListField label={parameter.kind === "categorical" ? "Categories" : "Allowed values"} hint="Comma-separated; at least two distinct values" values={((parameter.kind === "categorical" ? parameter.categories : parameter.values) as string[] | undefined) ?? []} onChange={(next) => changeParameter(index, { ...parameter, [parameter.kind === "categorical" ? "categories" : "values"]: next })} />}
          </div>
        </section>)}
        <Button disabled={parameters.length >= 12} onClick={() => update("parameters", [...parameters, { name: "", kind: "discrete", unit: "", values: [] }])}>Add parameter</Button>
      </fieldset>
      <fieldset><legend>Target & method</legend><div className="cs-form-grid">
        <TextField label="Target metric" value={String(target.name ?? "")} onChange={(e) => update("target", { ...target, name: e.target.value })} />
        <label className="cs-field"><span className="cs-field__label">Objective</span><select className="cs-select" value={String(target.mode ?? "maximize")} onChange={(e) => {
          const next: RecordValue = { ...target, mode: e.target.value }; if (e.target.value !== "match") delete next.match_bounds; update("target", next);
        }}>{["maximize", "minimize", "match"].map((mode) => <option key={mode}>{mode}</option>)}</select></label>
        <TextField label="Target unit" value={String(target.unit ?? "")} onChange={(e) => update("target", { ...target, unit: e.target.value })} />
        <TextField label="Reviewed method" value={String(target.method ?? "")} onChange={(e) => update("target", { ...target, method: e.target.value })} />
        {target.mode === "match" && <CommaListField label="Reviewed match cutoffs" hint="Two comma-separated cutoffs, lower then upper" values={(target.match_bounds as string[] | undefined) ?? []} onChange={(next) => update("target", { ...target, match_bounds: next })} />}
      </div></fieldset>
      <StructuredRows label="Linear constraints" advanced={false} value={JSON.stringify(spec.constraints ?? [])} onChange={(text) => update("constraints", JSON.parse(text))} maxRows={24} newRow={{ parameters: [], coefficients: [], operator: "<=", rhs: "" }} fields={[
        { key: "parameters", label: "Parameter names", kind: "list", hint: "Comma-separated; numerical parameters only" },
        { key: "coefficients", label: "Coefficients", kind: "numbers", hint: "One coefficient for each parameter, in the same order" },
        { key: "operator", label: "Constraint operator", options: ["=", ">=", "<="] },
        { key: "rhs", label: "Constraint limit" },
      ]} />
      <fieldset><legend>Recorded context</legend><p className="cs-field__hint">Keep grade, process, substrate and other conditions explicit. Enter both a key and its recorded value.</p>
        {Object.entries(context).map(([key, item], index) => <div className="cs-inline-form" key={index}>
          <TextField label="Context key" hint="Each context key must be unique" value={key} onChange={(e) => { if (e.target.value !== key && Object.hasOwn(context, e.target.value)) return; update("context", Object.fromEntries(Object.entries(context).map(([k, v], i) => i === index ? [e.target.value, v] : [k, v]))); }} />
          <TextField label="Context value" value={item} onChange={(e) => update("context", { ...context, [key]: e.target.value })} />
          <Button variant="ghost" onClick={() => { const next = { ...context }; delete next[key]; update("context", next); }}>Remove context</Button>
        </div>)}
        <Button disabled={Object.hasOwn(context, "")} onClick={() => update("context", { ...context, "": "" })}>Add context</Button>
      </fieldset>
      <div className="cs-form-grid">
        <TextField label="Reproducibility seed" type="number" min={0} max={4294967295} value={String(spec.seed ?? "")} onChange={(e) => update("seed", e.target.value === "" ? null : Number(e.target.value))} />
        <label className="cs-field"><span className="cs-field__label">Recommender</span><select className="cs-select" value={String(spec.recommender ?? "two_phase")} onChange={(e) => update("recommender", e.target.value)}><option value="random">Random</option><option value="two_phase">Two phase</option></select></label>
      </div>
    </>}
    <details className="cs-technical"><summary>Advanced: exact campaign definition</summary><p className="cs-field__hint">Use the exact payload for mixture totals and additional supported configuration. This replaces the structured definition; every constraint remains subject to server validation.</p><label className="cs-field"><span className="cs-field__label">Campaign definition JSON</span><textarea className="cs-input cs-mono" aria-label="Campaign definition JSON" rows={10} value={value} onChange={(e) => onChange(e.target.value)} /></label></details>
  </section>;
}
