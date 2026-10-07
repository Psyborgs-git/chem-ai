import { useState } from "react";
import { useMutation } from "react-relay";

import { Button } from "../../components/atoms/Button";
import { DecimalField } from "../../components/atoms/DecimalField";
import { TextField } from "../../components/atoms/TextField";
import { UnitSelect } from "../../components/atoms/UnitSelect";
import { InlineFinding } from "../../components/molecules/InlineFinding";
import { MaterialIdentityPicker, type Picked } from "./pickers";
import { RegistryRevisionDraftMutation } from "./operations";

import type { registryRevisionDraftMutation } from "../../__generated__/registryRevisionDraftMutation.graphql";

const AMOUNT_UNITS = [
  "mass_percent",
  "mass_fraction",
  "volume_percent",
  "volume_fraction",
  "mole_percent",
  "mole_fraction",
  "g",
  "kg",
  "mg",
  "L",
  "mL",
  "mol",
  "mmol",
] as const;

const BASES = ["as_supplied", "active_solids", "dry_weight", "wet_weight"] as const;

const FRACTION_UNITS = new Set([
  "mass_percent",
  "mass_fraction",
  "volume_percent",
  "volume_fraction",
  "mole_percent",
  "mole_fraction",
]);

interface IngredientRowState {
  key: number;
  materialId: string | null;
  materialLabel: string | null;
  name: string;
  value: string;
  unit: string;
  basis: string;
  role: string;
}

type Finding = { code?: string; message?: string; fieldPath?: string | null };
type Errs = readonly Finding[];

function emptyRow(key: number): IngredientRowState {
  return {
    key,
    materialId: null,
    materialLabel: null,
    name: "",
    value: "",
    unit: "mass_percent",
    basis: "as_supplied",
    role: "",
  };
}

/** Rebuild editor rows from a stored payload — the domain never
 * normalizes, so rows round-trip exactly what was saved. */
export function rowsFromPayload(payload: unknown): {
  rows: IngredientRowState[];
  amountBasis: string;
  declaredTotal: string;
  tolerance: string;
  completeness: string;
} {
  const p =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? (payload as Record<string, unknown>)
      : {};
  const list = Array.isArray(p.ingredients) ? p.ingredients : [];
  const rows = list.map((line, i) => {
    const l =
      line && typeof line === "object" && !Array.isArray(line)
        ? (line as Record<string, unknown>)
        : {};
    const amount =
      l.amount && typeof l.amount === "object"
        ? (l.amount as Record<string, unknown>)
        : {};
    const materialId = l.materialId != null ? String(l.materialId) : null;
    return {
      key: i,
      materialId,
      materialLabel: null,
      name:
        l.name != null
          ? String(l.name)
          : l.alias != null
            ? String(l.alias)
            : (materialId ?? ""),
      value: amount.value != null ? String(amount.value) : "",
      unit: amount.unit != null ? String(amount.unit) : "mass_percent",
      basis: amount.basis != null ? String(amount.basis) : "as_supplied",
      role: l.role != null ? String(l.role) : "",
    };
  });
  return {
    rows,
    amountBasis: p.amountBasis != null ? String(p.amountBasis) : "mass_percent",
    declaredTotal: p.declaredTotal != null ? String(p.declaredTotal) : "",
    tolerance: p.tolerance != null ? String(p.tolerance) : "",
    completeness:
      p.completeness != null ? String(p.completeness) : "draft",
  };
}

function IngredientRow({
  row,
  onChange,
  onRemove,
  onPickMaterial,
}: {
  row: IngredientRowState;
  onChange: (r: IngredientRowState) => void;
  onRemove: () => void;
  onPickMaterial: (p: Picked) => void;
}) {
  return (
    <li className="cs-formulation-editor__row" data-material-id={row.materialId ?? ""}>
      <TextField
        label="ingredient name"
        value={row.name}
        onChange={(e) => onChange({ ...row, name: e.target.value })}
        required={!row.materialId}
        hint={
          row.materialId
            ? `linked: ${row.materialLabel ?? row.materialId}`
            : "pick a material to link the canonical identity, or leave unlinked"
        }
      />
      <MaterialIdentityPicker
        label={`link material for ${row.name || "ingredient"}`}
        onPick={onPickMaterial}
      />
      <DecimalField
        label="amount"
        value={row.value}
        onValueChange={(v) => onChange({ ...row, value: v })}
      />
      <UnitSelect
        label="unit"
        value={row.unit}
        units={AMOUNT_UNITS}
        onValueChange={(u) => onChange({ ...row, unit: u })}
      />
      {FRACTION_UNITS.has(row.unit) && (
        <div className="cs-field">
          <label className="cs-field__label" htmlFor={`basis-${row.key}`}>
            basis
          </label>
          <select
            id={`basis-${row.key}`}
            className="cs-select"
            value={row.basis}
            onChange={(e) => onChange({ ...row, basis: e.target.value })}
          >
            {BASES.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </div>
      )}
      <TextField
        label="role"
        hint="solvent / binder / additive…"
        value={row.role}
        onChange={(e) => onChange({ ...row, role: e.target.value })}
      />
      <Button variant="ghost" onClick={onRemove}>
        remove ingredient
      </Button>
    </li>
  );
}

/** Structured formulation editor (PAR-07): ingredients list with a
 * material picker + quantity/role fields that drafts a real
 * FormulationRevision — no JSON editing. Drafts may be incomplete;
 * acceptance is the gate (§5). */
export function FormulationEditor({
  familyId,
  parentRevisionId,
  parentPayload,
  onSaved,
}: {
  /** GlobalID of the family this revision belongs to */
  familyId: string;
  /** raw uuid of the parent revision (encoded to GlobalID on save) */
  parentRevisionId?: string | null;
  /** parent payload to pre-fill from via "copy parent contents" */
  parentPayload?: unknown;
  onSaved?: () => void;
}) {
  const [commit, pending] =
    useMutation<registryRevisionDraftMutation>(RegistryRevisionDraftMutation);
  const [rows, setRows] = useState<IngredientRowState[]>([emptyRow(0)]);
  const [nextKey, setNextKey] = useState(1);
  const [amountBasis, setAmountBasis] = useState("mass_percent");
  const [declaredTotal, setDeclaredTotal] = useState("");
  const [tolerance, setTolerance] = useState("");
  const [completeness, setCompleteness] = useState("draft");
  const [substrateContext, setSubstrateContext] = useState("");
  const [applicationContext, setApplicationContext] = useState("");
  const [authorSource, setAuthorSource] = useState("manual");
  const [errors, setErrors] = useState<Errs>([]);
  const [findings, setFindings] = useState<readonly unknown[]>([]);
  const [saved, setSaved] = useState<string | null>(null);

  const copyParent = () => {
    if (parentPayload == null) return;
    const f = rowsFromPayload(parentPayload);
    setRows(f.rows.length > 0 ? f.rows : [emptyRow(0)]);
    setNextKey(f.rows.length);
    setAmountBasis(f.amountBasis);
    setDeclaredTotal(f.declaredTotal);
    setTolerance(f.tolerance);
    setCompleteness(f.completeness);
  };

  const save = () => {
    setErrors([]);
    setFindings([]);
    setSaved(null);
    const ingredients = rows
      .filter((r) => r.name.trim() || r.materialId || r.value)
      .map((r) => ({
        ...(r.materialId ? { materialId: r.materialId } : {}),
        ...(r.name.trim() ? { name: r.name.trim() } : {}),
        amount: {
          value: r.value,
          unit: r.unit,
          ...(FRACTION_UNITS.has(r.unit) ? { basis: r.basis } : {}),
        },
        ...(r.role.trim() ? { role: r.role.trim() } : {}),
      }));
    const payload: Record<string, unknown> = {
      ingredients,
      amountBasis,
      completeness,
      ...(declaredTotal ? { declaredTotal } : {}),
      ...(tolerance ? { tolerance } : {}),
      ...(substrateContext ? { substrateContext } : {}),
      ...(applicationContext ? { applicationContext } : {}),
      ...(authorSource ? { authorSource } : {}),
    };
    commit({
      variables: {
        input: {
          familyId,
          payload,
          parentRevisionId: parentRevisionId
            ? btoa(`FormulationRevision:${parentRevisionId}`)
            : undefined,
          idempotencyKey: `fw-formulation-${crypto.randomUUID()}`,
        },
      },
      onCompleted: (resp) => {
        const errs = resp.formulations.revisionDraft.errors ?? [];
        if (errs.length > 0) {
          setErrors(errs);
          return;
        }
        const rev = resp.formulations.revisionDraft.revision;
        const revFindings =
          (rev?.payload as { validationFindings?: unknown[] } | null)
            ?.validationFindings ?? [];
        setFindings(revFindings);
        setSaved(
          rev ? `draft rev ${rev.revision} saved (${rev.status})` : "saved",
        );
        onSaved?.();
      },
      onError: (e) =>
        setErrors([{ code: "NETWORK", message: `not saved: ${e.message}` }]),
    });
  };

  return (
    <section aria-label="formulation editor" className="cs-formulation-editor">
      <h3>structured formulation revision</h3>
      {parentPayload != null && (
        <p>
          <Button type="button" onClick={copyParent}>
            copy parent contents into the editor
          </Button>{" "}
          {parentRevisionId ? (
            <small>
              descends from <code>{parentRevisionId.slice(0, 8)}…</code>
            </small>
          ) : null}
        </p>
      )}
      <ul aria-label="ingredients">
        {rows.map((row) => (
          <IngredientRow
            key={row.key}
            row={row}
            onChange={(r) =>
              setRows((rs) => rs.map((x) => (x.key === r.key ? r : x)))
            }
            onRemove={() =>
              setRows((rs) =>
                rs.length > 1 ? rs.filter((x) => x.key !== row.key) : rs,
              )
            }
            onPickMaterial={(p) =>
              setRows((rs) =>
                rs.map((x) =>
                  x.key === row.key
                    ? {
                        ...x,
                        materialId: p.uuid,
                        materialLabel: p.label,
                        name: x.name || p.label.split(" · ")[0] || p.label,
                      }
                    : x,
                ),
              )
            }
          />
        ))}
      </ul>
      <Button
        type="button"
        onClick={() => {
          setRows((rs) => [...rs, emptyRow(nextKey)]);
          setNextKey((k) => k + 1);
        }}
      >
        add ingredient
      </Button>
      <fieldset>
        <legend>totals</legend>
        <div className="cs-field">
          <label className="cs-field__label" htmlFor="amount-basis">
            amount basis
          </label>
          <select
            id="amount-basis"
            className="cs-select"
            value={amountBasis}
            onChange={(e) => setAmountBasis(e.target.value)}
          >
            {AMOUNT_UNITS.filter((u) => FRACTION_UNITS.has(u)).map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
            <option value="as_supplied">as_supplied</option>
          </select>
        </div>
        <DecimalField
          label="declared total"
          hint="required for a complete recipe; optimizer baselines use 1"
          value={declaredTotal}
          onValueChange={setDeclaredTotal}
        />
        <TextField
          label="tolerance (optional)"
          hint="e.g. 0.5 — acceptance checks declaredTotal within tolerance"
          value={tolerance}
          onChange={(e) => setTolerance(e.target.value)}
        />
        <div className="cs-field">
          <label className="cs-field__label" htmlFor="completeness">
            completeness
          </label>
          <select
            id="completeness"
            className="cs-select"
            value={completeness}
            onChange={(e) => setCompleteness(e.target.value)}
          >
            <option value="draft">draft — may be incomplete</option>
            <option value="complete">complete — declared total enforced</option>
          </select>
        </div>
      </fieldset>
      <fieldset>
        <legend>context</legend>
        <TextField
          label="substrate context (optional)"
          value={substrateContext}
          onChange={(e) => setSubstrateContext(e.target.value)}
        />
        <TextField
          label="application context (optional)"
          value={applicationContext}
          onChange={(e) => setApplicationContext(e.target.value)}
        />
        <TextField
          label="author source"
          value={authorSource}
          onChange={(e) => setAuthorSource(e.target.value)}
        />
      </fieldset>
      {errors.map((e) => (
        <InlineFinding
          key={`${e.code}:${e.fieldPath ?? ""}:${e.message}`}
          severity="error"
          message={`${e.fieldPath ? `${e.fieldPath}: ` : ""}${e.message}`}
        />
      ))}
      {findings.map((f, i) => {
        const rec =
          f && typeof f === "object" ? (f as Record<string, unknown>) : {};
        return (
          <InlineFinding
            key={i}
            severity="warning"
            message={`${rec.code ?? "finding"}: ${rec.message ?? JSON.stringify(f)}`}
          />
        );
      })}
      {saved && (
        <p role="status" className="cs-formulation-editor__saved">
          {saved}
        </p>
      )}
      <Button variant="primary" disabled={pending} onClick={save}>
        {pending ? "saving…" : "save formulation draft"}
      </Button>
    </section>
  );
}
