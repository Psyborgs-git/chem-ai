import { useEffect, useId, useState } from "react";
import { Button } from "../atoms/Button";
import { TextField } from "../atoms/TextField";

type Field = {
  key: string; label: string; kind?: "text" | "number" | "boolean" | "list" | "numbers" | "messages";
  options?: readonly string[]; hint?: string;
};
type Row = Record<string, unknown>;

/** Keep separators while typing; serializing on each key must not eat a trailing comma. */
export function CommaListField({ label, hint, values, onChange }: {
  label: string; hint?: string; values: readonly unknown[]; onChange: (values: string[]) => void;
}) {
  const serialized = JSON.stringify(values);
  const [draft, setDraft] = useState(() => values.join(", "));
  useEffect(() => { setDraft((JSON.parse(serialized) as unknown[]).join(", ")); }, [serialized]);
  return <TextField label={label} hint={hint} value={draft} onChange={(e) => {
    setDraft(e.target.value);
    onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean));
  }} />;
}

/** Structured controls retain unedited fields and expose the exact payload for advanced workflows. */
export function StructuredRows({ label, value, onChange, fields, newRow, maxRows = 100, advanced = true }: {
  label: string; value: string; onChange: (value: string) => void; fields: readonly Field[]; newRow: Row; maxRows?: number; advanced?: boolean;
}) {
  const id = useId();
  let rows: Row[] = [];
  let invalid = false;
  try {
    const parsed: unknown = value.trim() ? JSON.parse(value) : [];
    if (!Array.isArray(parsed) || parsed.some((r) => !r || typeof r !== "object" || Array.isArray(r))) invalid = true;
    else rows = parsed as Row[];
  } catch { invalid = true; }
  const write = (next: Row[]) => onChange(JSON.stringify(next, null, 2));
  const update = (index: number, key: string, next: unknown) => write(rows.map((r, i) => i === index ? { ...r, [key]: next } : r));
  return <fieldset className="cs-rows-editor"><legend>{label}</legend>
    {invalid ? <p role="alert" className="cs-field__error">The advanced payload must be a JSON array of records. Correct it below to use the row editor.</p> : <>
      {rows.length === 0 && <p className="cs-field__hint">No {label.toLowerCase()} added yet.</p>}
      {rows.map((row, index) => <section className="cs-rows-editor__row" key={index} aria-label={`${label} ${index + 1}`}>
        <header className="cs-list__row"><strong>{label} {index + 1}</strong><Button variant="ghost" onClick={() => write(rows.filter((_, i) => i !== index))} aria-label={`Remove ${label.toLowerCase()} ${index + 1}`}>Remove</Button></header>
        <div className="cs-form-grid">{fields.map((field) => {
          const fieldId = `${id}-${index}-${field.key}`;
          const current = row[field.key];
          if (field.kind === "messages") {
            const messages = Array.isArray(current) ? current as Row[] : [];
            return <fieldset key={field.key} className="cs-form-span"><legend>{field.label}</legend>
              {messages.map((message, mi) => <div className="cs-message-editor" key={mi}>
                <label className="cs-field"><span className="cs-field__label">Message role</span><select className="cs-select" value={String(message.role ?? "user")} onChange={(e) => update(index, field.key, messages.map((m, i) => mi === i ? { ...m, role: e.target.value } : m))}>{["user", "system", "tool"].map((role) => <option key={role}>{role}</option>)}</select></label>
                <label className="cs-field"><span className="cs-field__label">Message content</span><textarea className="cs-input" rows={3} value={String(message.content ?? "")} onChange={(e) => update(index, field.key, messages.map((m, i) => mi === i ? { ...m, content: e.target.value } : m))} /></label>
                <Button variant="ghost" aria-label={`Remove message ${mi + 1}`} onClick={() => update(index, field.key, messages.filter((_, i) => mi !== i))}>Remove message</Button>
              </div>)}
              <Button onClick={() => update(index, field.key, [...messages, { role: "user", content: "" }])}>Add message</Button>
            </fieldset>;
          }
          if (field.kind === "boolean") return <label className="cs-checkbox" key={field.key}><input type="checkbox" checked={current === true} onChange={(e) => update(index, field.key, e.target.checked)} />{field.label}</label>;
          if (field.options) return <div className="cs-field" key={field.key}><label htmlFor={fieldId} className="cs-field__label">{field.label}</label><select id={fieldId} className="cs-select" value={String(current ?? "")} onChange={(e) => update(index, field.key, e.target.value)}><option value="">Select…</option>{field.options.map((o) => <option key={o} value={o}>{o.replaceAll("_", " ")}</option>)}</select></div>;
          if (field.kind === "text") return <div className="cs-field cs-form-span" key={field.key}><label htmlFor={fieldId} className="cs-field__label">{field.label}</label><textarea id={fieldId} className="cs-input" rows={3} value={String(current ?? "")} onChange={(e) => update(index, field.key, e.target.value)} />{field.hint && <p className="cs-field__hint">{field.hint}</p>}</div>;
          const list = field.kind === "list" || field.kind === "numbers";
          if (list) return <CommaListField key={field.key} label={field.label} hint={field.hint} values={Array.isArray(current) ? current : []} onChange={(next) => update(index, field.key, next)} />;
          return <TextField key={field.key} label={field.label} hint={field.hint} value={String(current ?? "")} type={field.kind === "number" ? "number" : "text"} step={field.kind === "number" ? "any" : undefined} onChange={(e) => {
            const text = e.target.value;
            update(index, field.key, field.kind === "number" ? (text === "" ? null : Number(text)) : text);
          }} />;
        })}</div>
      </section>)}
      <Button disabled={rows.length >= maxRows} onClick={() => write([...rows, structuredClone(newRow)])}>Add {label.toLowerCase()}</Button>
    </>}
    {advanced && <details className="cs-technical"><summary>Advanced: edit {label.toLowerCase()} payload</summary><label className="cs-field"><span className="cs-field__label">{label} (JSON array)</span><textarea className="cs-input cs-mono" rows={5} value={value} onChange={(e) => onChange(e.target.value)} /></label></details>}
  </fieldset>;
}
