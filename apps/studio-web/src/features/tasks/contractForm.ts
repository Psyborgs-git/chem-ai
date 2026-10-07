/** Canonical success-contract form model (PAR-01).
 *
 * The form speaks the pack vocabulary — `metrics` + `hard_constraints`
 * + `unknowns` — the same DTO the domain validates, the GraphQL
 * mutations carry, fixtures seed and the evaluator reads. Persisted
 * legacy shapes (`requiredMetrics` with nested `target: {value,unit}`,
 * `{name, target: ">= 500 mPa·s"}`, bare `constraints` lists) hydrate
 * into the same form and are converted to the canonical schema on the
 * next save — the stored revision itself is never rewritten.
 */

export interface MetricForm {
  key: string;
  id: string;
  label: string;
  required: boolean;
  valueKind: string;
  operator: string;
  /** comma-separated for multi-bound operators (between/tolerance) */
  targetValues: string;
  unit: string;
  methodRevisionId: string;
  conditions: string;
  requiredEvidence: string[];
  aggregation: string;
  minIndependentBatches: string;
}

export interface ConstraintForm {
  key: string;
  id: string;
  text: string;
}

export interface ContractForm {
  metrics: MetricForm[];
  constraints: ConstraintForm[];
  unknowns: string[];
  /** hydrated from a `requiredMetrics` payload — save converts to
   * canonical; the banner tells the user the conversion is explicit */
  legacy: boolean;
}

/** unit whitelist from domain.lab.units — the only vocabulary the
 * evaluator can compare; an empty choice stays a missing unit */
export const CONTRACT_UNITS = [
  "",
  "mPa·s",
  "cP",
  "Pa·s",
  "mass_fraction",
  "mass_percent",
  "%",
  "g",
  "kg",
  "mL",
  "L",
  "s",
  "min",
  "h",
  "°C",
  "K",
  "°F",
  "dimensionless",
  "1",
] as const;

export const CONTRACT_OPERATORS = [
  { value: "gte", label: "≥ (gte)" },
  { value: "lte", label: "≤ (lte)" },
  { value: "gt", label: "> (gt)" },
  { value: "lt", label: "< (lt)" },
  { value: "eq", label: "= (eq)" },
  { value: "between", label: "between (low, high)" },
  { value: "within_tolerance", label: "within tolerance" },
  { value: "categorical_match", label: "categorical match" },
] as const;

export const EVIDENCE_CLASSES = [
  "lab_measurement",
  "replication",
  "source_report",
  "physics_prediction",
  "learned_prediction",
] as const;

export const AGGREGATIONS = [
  { value: "", label: "not declared" },
  { value: "single", label: "single" },
  { value: "fixture-single-value", label: "fixture-single-value" },
  { value: "min", label: "min" },
  { value: "max", label: "max" },
  { value: "mean", label: "mean" },
] as const;

let seq = 0;
const nextKey = () => `k${++seq}`;

export const emptyMetric = (): MetricForm => ({
  key: nextKey(),
  id: "",
  label: "",
  required: true,
  valueKind: "numeric",
  operator: "gte",
  targetValues: "",
  unit: "",
  methodRevisionId: "",
  conditions: "",
  requiredEvidence: ["lab_measurement"],
  aggregation: "",
  minIndependentBatches: "",
});

export const emptyForm = (): ContractForm => ({
  metrics: [emptyMetric()],
  constraints: [],
  unknowns: [],
  legacy: false,
});

const asStr = (v: unknown): string => (typeof v === "string" ? v : "");
const asStrArr = (v: unknown): string[] =>
  Array.isArray(v) ? v.map(asStr).filter(Boolean) : [];

const LEGACY_OP: Record<string, string> = {
  ">=": "gte",
  "<=": "lte",
  ">": "gt",
  "<": "lt",
  "=": "eq",
};

/** parse a loose `{name, target: ">= 500 mPa·s"}` bound string */
const parseTargetString = (
  t: string,
): { operator: string; targetValues: string; unit: string } => {
  const m = t.match(/^\s*(>=|<=|>|<|=)\s*(\S+)\s*(.*)$/);
  if (!m) return { operator: "gte", targetValues: t.trim(), unit: "" };
  return {
    operator: LEGACY_OP[m[1]] ?? "gte",
    targetValues: m[2],
    unit: m[3]?.trim() ?? "",
  };
};

function metricFromAny(raw: unknown): MetricForm | null {
  if (typeof raw !== "object" || raw === null) return null;
  const m = raw as Record<string, unknown>;
  const form = emptyMetric();
  form.id = asStr(m.id) || asStr(m.name);
  form.label = asStr(m.label) || asStr(m.name);
  if (typeof m.required === "boolean") form.required = m.required;
  form.valueKind = asStr(m.value_kind) || "numeric";
  form.unit = asStr(m.unit);
  form.methodRevisionId = asStr(m.method_revision_id);
  const cond = m.conditions;
  if (typeof cond === "object" && cond !== null) {
    form.conditions = asStr((cond as Record<string, unknown>).description);
  }
  const ev = asStrArr(m.required_evidence ?? m.requiredEvidence);
  if (ev.length) form.requiredEvidence = ev;
  form.aggregation = asStr(m.aggregation);
  const rep = m.replication_rule ?? m.replicationRule;
  if (typeof rep === "object" && rep !== null) {
    const n = (rep as Record<string, unknown>).minIndependentBatches;
    if (typeof n === "number" || typeof n === "string")
      form.minIndependentBatches = String(n);
  } else if (typeof rep === "string") {
    form.minIndependentBatches = rep;
  }

  const tvs = asStrArr(m.target_values ?? m.targetValues);
  if (tvs.length) form.targetValues = tvs.join(", ");
  const op = asStr(m.operator);
  if (op && LEGACY_OP[op]) form.operator = LEGACY_OP[op];
  else if (op) form.operator = op;

  // loose persisted bound `target: ">= 500 mPa·s"`
  if (typeof m.target === "string") {
    const parsed = parseTargetString(m.target);
    if (parsed.operator) form.operator = parsed.operator;
    if (!form.targetValues) form.targetValues = parsed.targetValues;
    if (!form.unit) form.unit = parsed.unit;
  } else if (typeof m.target === "object" && m.target !== null) {
    // legacy UI bound `target: {value, unit}` — operator ">="/"<="/"target"
    const t = m.target as Record<string, unknown>;
    const v = asStr(t.value);
    if (v && !form.targetValues) form.targetValues = v;
    const u = asStr(t.unit);
    if (u && !form.unit) form.unit = u;
    if (op === "target") form.operator = "eq"; // reached by review, surfaced
  }
  return form;
}

function constraintFromAny(raw: unknown): ConstraintForm | null {
  if (typeof raw === "string")
    return { key: nextKey(), id: "", text: raw };
  if (typeof raw !== "object" || raw === null) return null;
  const c = raw as Record<string, unknown>;
  return {
    key: nextKey(),
    id: asStr(c.id),
    text: asStr(c.text) || asStr(c.description),
  };
}

/** payload → editable form (canonical + persisted legacy shapes) */
export function formFromPayload(payload: unknown): ContractForm {
  const form = emptyForm();
  form.metrics = [];
  if (typeof payload !== "object" || payload === null) {
    form.legacy = true;
    return form;
  }
  const p = payload as Record<string, unknown>;
  const canonical = Array.isArray(p.metrics) ? p.metrics : [];
  const legacyList = Array.isArray(p.requiredMetrics) ? p.requiredMetrics : [];
  // canonical vocabulary wins when both exist — legacy entries are
  // preserved in the stored revision, not re-edited here
  const source = canonical.length ? canonical : legacyList;
  form.legacy = !canonical.length && legacyList.length > 0;
  form.metrics = source
    .map(metricFromAny)
    .filter((m): m is MetricForm => m !== null);
  const gates = [
    ...(Array.isArray(p.hard_constraints) ? p.hard_constraints : []),
    ...(Array.isArray(p.hardConstraints) ? p.hardConstraints : []),
    ...(Array.isArray(p.constraints) ? p.constraints : []),
  ];
  form.constraints = gates
    .map(constraintFromAny)
    .filter((c): c is ConstraintForm => c !== null);
  form.unknowns = asStrArr(p.unknowns);
  return form;
}

const nonEmpty = (s: string) => s.trim() !== "";

/** form → canonical payload (extra fields are never emitted;
 * nothing missing is filled with a scientific default — absent
 * method/conditions/aggregation stay explicit nulls) */
export function payloadFromForm(form: ContractForm): Record<string, unknown> {
  return {
    schema_version: "1.0.0",
    fixture_only: true,
    metrics: form.metrics.map((m) => ({
      id: m.id.trim() || null,
      label: m.label.trim() || m.id.trim() || null,
      required: m.required,
      value_kind: m.valueKind,
      operator: m.operator,
      target_values: m.targetValues
        .split(",")
        .map((v) => v.trim())
        .filter(nonEmpty),
      unit: m.unit || null,
      method_revision_id: m.methodRevisionId.trim() || null,
      conditions: {
        substrate_revision_id: null,
        description: m.conditions.trim(),
      },
      required_evidence: m.requiredEvidence,
      aggregation: m.aggregation || null,
      replication_rule: m.minIndependentBatches.trim()
        ? { minIndependentBatches: Number(m.minIndependentBatches.trim()) }
        : null,
    })),
    hard_constraints: form.constraints.map((c) => ({
      id: c.id.trim() || null,
      text: c.text.trim(),
    })),
    unknowns: form.unknowns,
  };
}

/** Unsaved-form store that survives the editor unmounting on
 * section/route switches — changes are never silently lost (§22.4).
 * Cleared on a confirmed save. */
const pendingForms = new Map<string, ContractForm>();

export const pendingForm = {
  get: (taskId: string) => pendingForms.get(taskId),
  set: (taskId: string, form: ContractForm) => pendingForms.set(taskId, form),
  clear: (taskId: string) => pendingForms.delete(taskId),
};
