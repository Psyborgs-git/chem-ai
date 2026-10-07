import { Suspense } from "react";
import { useLazyLoadQuery } from "react-relay";

import { Badge } from "../../components/atoms/Badge";
import { EmptyState, LoadingState } from "../../components/states/states";
import { ingredientDiff, metaDiff, processStepDiff } from "./diff";
import { RegistryRevisionNodesQuery } from "./operations";

import type { registryRevisionNodesQuery } from "../../__generated__/registryRevisionNodesQuery.graphql";

const TONE: Record<string, "info" | "success" | "warning" | "danger" | "neutral"> =
  {
    added: "success",
    removed: "danger",
    changed: "warning",
    unchanged: "neutral",
  };

function gid(type: string, uuid: string): string {
  return btoa(`${type}:${uuid}`);
}

function toPayload(node: unknown): Record<string, unknown> | null {
  const n = node as { payload?: unknown } | null;
  if (n && n.payload && typeof n.payload === "object") {
    return n.payload as Record<string, unknown>;
  }
  return null;
}

function amountText(a: { value?: string; unit?: string; basis?: string } | null) {
  if (!a) return "—";
  return `${a.value ?? "?"} ${a.unit ?? ""}${a.basis ? ` (${a.basis})` : ""}`.trim();
}

function IngredientTable({
  left,
  right,
}: {
  left: Record<string, unknown> | null;
  right: Record<string, unknown> | null;
}) {
  const rows = ingredientDiff(left, right);
  if (rows.length === 0) {
    return <EmptyState title="no ingredients recorded on either revision" />;
  }
  return (
    <table className="cs-diff-table" data-field="ingredient-diff">
      <caption>ingredients</caption>
      <thead>
        <tr>
          <th scope="col">ingredient</th>
          <th scope="col">change</th>
          <th scope="col">baseline</th>
          <th scope="col">candidate</th>
          <th scope="col">detail</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} data-status={r.status}>
            <td>{r.name}</td>
            <td>
              <Badge tone={TONE[r.status]}>{r.status}</Badge>
            </td>
            <td>
              {amountText(r.left?.amount ?? null)}
              {r.left?.role ? ` · ${r.left.role}` : ""}
            </td>
            <td>
              {amountText(r.right?.amount ?? null)}
              {r.right?.role ? ` · ${r.right.role}` : ""}
            </td>
            <td>{r.changes.join("; ") || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ProcessTable({
  left,
  right,
}: {
  left: Record<string, unknown> | null;
  right: Record<string, unknown> | null;
}) {
  if (!left && !right) return null;
  const rows = processStepDiff(left, right);
  if (rows.length === 0) return null;
  return (
    <table className="cs-diff-table" data-field="process-diff">
      <caption>process steps (order is significant)</caption>
      <thead>
        <tr>
          <th scope="col">#</th>
          <th scope="col">change</th>
          <th scope="col">baseline step</th>
          <th scope="col">candidate step</th>
          <th scope="col">detail</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.index} data-status={r.status}>
            <td>{r.left?.order ?? r.right?.order}</td>
            <td>
              <Badge tone={TONE[r.status]}>{r.status}</Badge>
            </td>
            <td>
              {r.left ? `${r.left.action}${r.left.detail ? ` (${r.left.detail})` : ""}` : "—"}
            </td>
            <td>
              {r.right ? `${r.right.action}${r.right.detail ? ` (${r.right.detail})` : ""}` : "—"}
            </td>
            <td>{r.changes.join("; ") || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ProcessDiff({
  leftProcId,
  rightProcId,
}: {
  leftProcId: string | null;
  rightProcId: string | null;
}) {
  const ids = [leftProcId, rightProcId]
    .filter((v): v is string => v != null)
    .map((v) => gid("ProcessRevision", v));
  const data = useLazyLoadQuery<registryRevisionNodesQuery>(
    RegistryRevisionNodesQuery,
    { ids },
    { fetchPolicy: "network-only" },
  );
  const nodes = data.nodes ?? [];
  const left = leftProcId
    ? toPayload(nodes.find((n) => n?.id === gid("ProcessRevision", leftProcId)))
    : null;
  const right = rightProcId
    ? toPayload(nodes.find((n) => n?.id === gid("ProcessRevision", rightProcId)))
    : null;
  return <ProcessTable left={left} right={right} />;
}

function diffNode(
  nodes: readonly (unknown | null)[],
  type: string,
  uuid: string,
): unknown {
  return nodes.find((n) => (n as { id?: string } | null)?.id === gid(type, uuid));
}

function nodeParentUuid(node: unknown): string | null {
  const p = (node as { parentRevisionId?: string | null } | null)
    ?.parentRevisionId;
  return p ?? null;
}

/** Baseline side of the diff — resolves the candidate's stored
 * parentRevisionId (uuid) when no explicit baseline was given. */
function BaselineSide({
  leftUuid,
  right,
}: {
  leftUuid: string | null;
  right: Record<string, unknown> | null;
}) {
  const data = useLazyLoadQuery<registryRevisionNodesQuery>(
    RegistryRevisionNodesQuery,
    { ids: leftUuid ? [gid("FormulationRevision", leftUuid)] : [] },
    { fetchPolicy: "network-only" },
  );
  const left = leftUuid
    ? toPayload(diffNode(data.nodes ?? [], "FormulationRevision", leftUuid))
    : null;
  const meta = metaDiff(left, right);
  const leftProc = left?.processRevisionId;
  const rightProc = right?.processRevisionId;
  return (
    <div className="cs-diff" role="group" aria-label="revision diff">
      {meta.length > 0 && (
        <table className="cs-diff-table" data-field="meta-diff">
          <caption>revision metadata</caption>
          <thead>
            <tr>
              <th scope="col">field</th>
              <th scope="col">baseline</th>
              <th scope="col">candidate</th>
            </tr>
          </thead>
          <tbody>
            {meta.map((r) => (
              <tr key={r.field} data-status={r.changed ? "changed" : "unchanged"}>
                <td>{r.field}</td>
                <td>
                  <code>{r.left}</code>
                </td>
                <td>
                  <code>{r.right}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <IngredientTable left={left} right={right} />
      {leftProc || rightProc ? (
        <Suspense fallback={<LoadingState label="loading process diff…" />}>
          <ProcessDiff
            leftProcId={leftProc != null ? String(leftProc) : null}
            rightProcId={rightProc != null ? String(rightProc) : null}
          />
        </Suspense>
      ) : null}
    </div>
  );
}

function DiffBody({ rightUuid, leftUuid }: { rightUuid: string; leftUuid: string | null }) {
  const data = useLazyLoadQuery<registryRevisionNodesQuery>(
    RegistryRevisionNodesQuery,
    { ids: [gid("FormulationRevision", rightUuid)] },
    { fetchPolicy: "network-only" },
  );
  const rightNode = diffNode(data.nodes ?? [], "FormulationRevision", rightUuid);
  const right = toPayload(rightNode);
  const effectiveLeft = leftUuid ?? nodeParentUuid(rightNode);
  return (
    <Suspense fallback={<LoadingState label="loading baseline…" />}>
      <BaselineSide
        leftUuid={effectiveLeft}
        right={right}
      />
    </Suspense>
  );
}

/** Compare a candidate formulation revision against its baseline —
 * ingredients and process rendered as added/removed/changed rows,
 * never as raw JSON (§PAR-07). The baseline defaults to the
 * candidate's own parent revision — lineage is the diff. */
export function RevisionDiff({
  baselineUuid,
  candidateUuid,
}: {
  /** uuid of the baseline revision; null resolves the candidate's parent */
  baselineUuid: string | null;
  /** uuid of the candidate revision under review */
  candidateUuid: string;
}) {
  return (
    <Suspense fallback={<LoadingState label="loading diff…" />}>
      <DiffBody rightUuid={candidateUuid} leftUuid={baselineUuid} />
    </Suspense>
  );
}
