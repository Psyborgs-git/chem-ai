/**
 * Revision diff logic (PAR-07) — pure functions over formulation and
 * process payloads so the review surface renders added/removed/
 * changed rows instead of JSON dumps. Mirrors the domain's identity
 * rules: ingredient identity = materialId || alias || name; process
 * order is significant (reordering is a change).
 */

export type DiffStatus = "added" | "removed" | "changed" | "unchanged";

export interface AmountView {
  value?: string;
  unit?: string;
  basis?: string;
}

export interface IngredientView {
  key: string;
  name: string;
  amount: AmountView | null;
  role?: string;
}

export interface IngredientDiffRow {
  key: string;
  name: string;
  status: DiffStatus;
  changes: string[];
  left: IngredientView | null;
  right: IngredientView | null;
}

export interface StepView {
  order: string;
  action: string;
  detail: string;
}

export interface StepDiffRow {
  index: number;
  status: DiffStatus;
  changes: string[];
  left: StepView | null;
  right: StepView | null;
}

export interface MetaDiffRow {
  field: string;
  left: string;
  right: string;
  changed: boolean;
}

type Payload = Record<string, unknown>;

function asRecord(v: unknown): Payload | null {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Payload)
    : null;
}

function asAmount(v: unknown): AmountView | null {
  const r = asRecord(v);
  if (!r) return null;
  return {
    value: r.value != null ? String(r.value) : undefined,
    unit: r.unit != null ? String(r.unit) : undefined,
    basis: r.basis != null ? String(r.basis) : undefined,
  };
}

export function ingredientKey(line: Payload): string {
  const ident = line.materialId ?? line.alias ?? line.name;
  return ident != null ? String(ident) : "unidentified";
}

export function parseIngredients(payload: unknown): IngredientView[] {
  const p = asRecord(payload);
  const list = Array.isArray(p?.ingredients) ? p.ingredients : [];
  return list
    .map((line): IngredientView | null => {
      const l = asRecord(line);
      if (!l) return null;
      const key = ingredientKey(l);
      const name =
        l.name != null
          ? String(l.name)
          : l.alias != null
            ? String(l.alias)
            : key === "unidentified"
              ? "unidentified"
              : `material ${key.slice(0, 8)}…`;
      return {
        key,
        name,
        amount: asAmount(l.amount),
        role: l.role != null ? String(l.role) : undefined,
      };
    })
    .filter((v): v is IngredientView => v != null);
}

function amountText(a: AmountView | null): string {
  if (!a) return "—";
  return `${a.value ?? "?"} ${a.unit ?? ""}${a.basis ? ` (${a.basis})` : ""}`.trim();
}

function amountChanges(left: AmountView | null, right: AmountView | null): string[] {
  const changes: string[] = [];
  for (const f of ["value", "unit", "basis"] as const) {
    const l = left?.[f];
    const r = right?.[f];
    if (l !== r && (l != null || r != null)) {
      changes.push(`${f}: ${l ?? "—"} → ${r ?? "—"}`);
    }
  }
  return changes;
}

/** Order-independent ingredient diff — the same materialId/alias/name
 * keys left and right to added/removed/changed rows (§6.2). */
export function ingredientDiff(
  leftPayload: unknown,
  rightPayload: unknown,
): IngredientDiffRow[] {
  const left = new Map(parseIngredients(leftPayload).map((i) => [i.key, i]));
  const right = new Map(parseIngredients(rightPayload).map((i) => [i.key, i]));
  const keys = [...new Set([...left.keys(), ...right.keys()])];
  const rows: IngredientDiffRow[] = [];
  for (const key of keys) {
    const l = left.get(key) ?? null;
    const r = right.get(key) ?? null;
    if (l && !r) {
      rows.push({
        key,
        name: l.name,
        status: "removed",
        changes: [`was ${amountText(l.amount)}`],
        left: l,
        right: null,
      });
    } else if (!l && r) {
      rows.push({
        key,
        name: r.name,
        status: "added",
        changes: [`now ${amountText(r.amount)}`],
        left: null,
        right: r,
      });
    } else if (l && r) {
      const changes = [
        ...amountChanges(l.amount, r.amount),
        ...(l.role !== r.role && (l.role || r.role)
          ? [`role: ${l.role ?? "—"} → ${r.role ?? "—"}`]
          : []),
      ];
      rows.push({
        key,
        name: r.name,
        status: changes.length > 0 ? "changed" : "unchanged",
        changes,
        left: l,
        right: r,
      });
    }
  }
  return rows;
}

const META_FIELDS: readonly { field: string; label: string }[] = [
  { field: "declaredTotal", label: "declared total" },
  { field: "amountBasis", label: "amount basis" },
  { field: "tolerance", label: "tolerance" },
  { field: "completeness", label: "completeness" },
  { field: "processRevisionId", label: "process revision" },
];

export function metaDiff(
  leftPayload: unknown,
  rightPayload: unknown,
): MetaDiffRow[] {
  const l = asRecord(leftPayload) ?? {};
  const r = asRecord(rightPayload) ?? {};
  return META_FIELDS.map(({ field, label }) => {
    const lv = l[field];
    const rv = r[field];
    return {
      field: label,
      left: lv != null ? String(lv) : "—",
      right: rv != null ? String(rv) : "—",
      changed: lv !== rv && !(lv == null && rv == null),
    };
  }).filter((row) => row.left !== "—" || row.right !== "—" || row.changed);
}

function stepView(step: unknown, index: number): StepView {
  const s = asRecord(step) ?? {};
  const order = s.order != null ? String(s.order) : String(index + 1);
  const action = s.action != null ? String(s.action) : "—";
  const extras = Object.entries(s)
    .filter(([k]) => k !== "order" && k !== "action")
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  return { order, action, detail: extras };
}

/** Order-significant step diff — a reordered step shows as changed
 * at every displaced position (AT-0204-3). */
export function processStepDiff(
  leftPayload: unknown,
  rightPayload: unknown,
): StepDiffRow[] {
  const l = asRecord(leftPayload);
  const r = asRecord(rightPayload);
  const ls = Array.isArray(l?.steps) ? l.steps : [];
  const rs = Array.isArray(r?.steps) ? r.steps : [];
  const n = Math.max(ls.length, rs.length);
  const rows: StepDiffRow[] = [];
  for (let i = 0; i < n; i += 1) {
    const lv = i < ls.length ? stepView(ls[i], i) : null;
    const rv = i < rs.length ? stepView(rs[i], i) : null;
    if (lv && !rv) {
      rows.push({
        index: i,
        status: "removed",
        changes: [`removed step ${lv.order}: ${lv.action}`],
        left: lv,
        right: null,
      });
    } else if (!lv && rv) {
      rows.push({
        index: i,
        status: "added",
        changes: [`added step ${rv.order}: ${rv.action}`],
        left: null,
        right: rv,
      });
    } else if (lv && rv) {
      const changes: string[] = [];
      if (lv.action !== rv.action) {
        changes.push(`action: ${lv.action} → ${rv.action}`);
      }
      if (lv.order !== rv.order) {
        changes.push(`order: ${lv.order} → ${rv.order}`);
      }
      if (lv.detail !== rv.detail) {
        changes.push(
          `details: ${lv.detail || "—"} → ${rv.detail || "—"}`,
        );
      }
      rows.push({
        index: i,
        status: changes.length > 0 ? "changed" : "unchanged",
        changes,
        left: lv,
        right: rv,
      });
    }
  }
  return rows;
}
