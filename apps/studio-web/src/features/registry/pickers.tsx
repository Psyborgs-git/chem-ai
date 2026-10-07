import { Suspense, useEffect, useId, useState } from "react";
import { useLazyLoadQuery } from "react-relay";

import { TextField } from "../../components/atoms/TextField";
import { rawUuid } from "../../relay/network";
import { ContractRevisionsQuery } from "../tasks/operations";
import {
  RegistryFormulationRevisionsQuery,
  RegistryIdentitiesQuery,
  RegistryProductsQuery,
} from "./operations";
import { CandidateRevisionPickerQuery } from "../candidates/operations";

import type { candidatesRevisionPickerQuery } from "../../__generated__/candidatesRevisionPickerQuery.graphql";
import type { registryFormulationRevisionsQuery } from "../../__generated__/registryFormulationRevisionsQuery.graphql";
import type { registryIdentitiesQuery } from "../../__generated__/registryIdentitiesQuery.graphql";
import type { registryProductsQuery } from "../../__generated__/registryProductsQuery.graphql";
import type { tasksContractRevisionsQuery } from "../../__generated__/tasksContractRevisionsQuery.graphql";

/** What a picker resolves to: the canonical GlobalID for display,
 * plus the raw uuid for payload fields that store bare revision
 * ids (modeInputs, candidate.entityRevisionId, plan.payload). */
export type Picked = { globalId: string; uuid: string; label: string };

function useDebounced(value: string, ms: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function PickerList({
  listId,
  options,
  onPick,
  searching,
}: {
  listId: string;
  options: readonly Picked[];
  searching: boolean;
  onPick: (p: Picked) => void;
}) {
  if (options.length === 0) {
    return (
      <p className="cs-registry-picker__empty" role="status">
        {searching ? "no matches" : "start typing to search"}
      </p>
    );
  }
  return (
    <ul id={listId} role="listbox" className="cs-registry-picker__list">
      {options.map((o) => (
        <li key={o.globalId} role="option" aria-selected={false}>
          <button type="button" onClick={() => onPick(o)}>
            {o.label}
          </button>
        </li>
      ))}
    </ul>
  );
}

function PickerShell({
  label,
  hint,
  term,
  onTerm,
  picked,
  onClear,
  listId,
  expanded,
  readOnly = false,
  children,
}: {
  label: string;
  hint?: string;
  term: string;
  onTerm: (v: string) => void;
  picked: Picked | null;
  onClear: () => void;
  listId: string;
  expanded: boolean;
  /** fixed-option pickers render the field read-only — it announces
   * the launcher, it does not filter */
  readOnly?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="cs-registry-picker">
      <TextField
        label={label}
        hint={hint}
        value={term}
        onChange={(e) => onTerm(e.target.value)}
        role="combobox"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        readOnly={readOnly}
      />
      {picked ? (
        <p className="cs-registry-picker__picked" data-picked="true">
          selected: <strong>{picked.label}</strong>{" "}
          <button type="button" onClick={onClear}>
            change
          </button>
        </p>
      ) : (
        children
      )}
    </div>
  );
}

function IdentityPickerResults({
  listId,
  search,
  onPick,
}: {
  listId: string;
  search: string;
  onPick: (p: Picked) => void;
}) {
  const data = useLazyLoadQuery<registryIdentitiesQuery>(
    RegistryIdentitiesQuery,
    { search: search || null, first: 20 },
    { fetchPolicy: "network-only" },
  );
  const options = data.materialIdentities.edges.map((e) => {
    const n = e.node;
    const ids =
      (n.identifiers as
        | readonly { scheme?: string; value?: string }[]
        | null) ?? [];
    const idText = ids
      .map((i) => `${i.scheme ?? ""}:${i.value ?? ""}`)
      .filter((s) => s.length > 1)
      .join(", ");
    return {
      globalId: n.id,
      uuid: rawUuid(n.id),
      label: `${n.name} · ${n.kind}${idText ? ` · ${idText}` : ""}`,
    };
  });
  return (
    <PickerList
      listId={listId}
      options={options}
      searching={search.length > 0}
      onPick={onPick}
    />
  );
}

/** Material identity search — typeahead over the registry; selects
 * the canonical identity (§6.2: identity never name-only). */
export function MaterialIdentityPicker({
  label = "material",
  hint,
  onPick,
}: {
  label?: string;
  hint?: string;
  onPick: (p: Picked) => void;
}) {
  const listId = useId();
  const [term, setTerm] = useState("");
  const [picked, setPicked] = useState<Picked | null>(null);
  const search = useDebounced(term, 250);
  return (
    <PickerShell
      label={label}
      hint={hint ?? "search by name or identifier — no ids to copy"}
      term={term}
      onTerm={setTerm}
      picked={picked}
      onClear={() => setPicked(null)}
      listId={listId}
      expanded={!picked && search.length > 0}
    >
      <Suspense fallback={<p role="status">searching…</p>}>
        <IdentityPickerResults
          listId={listId}
          search={search}
          onPick={(p) => {
            setPicked(p);
            onPick(p);
          }}
        />
      </Suspense>
    </PickerShell>
  );
}

function ProductPickerResults({
  listId,
  search,
  onPick,
}: {
  listId: string;
  search: string;
  onPick: (p: Picked) => void;
}) {
  const data = useLazyLoadQuery<registryProductsQuery>(
    RegistryProductsQuery,
    { search: search || null, first: 20 },
    { fetchPolicy: "network-only" },
  );
  const options = data.referenceProducts.edges.map((e) => {
    const n = e.node;
    return {
      globalId: n.id,
      uuid: rawUuid(n.id),
      label: `${n.name}${n.supplier ? ` · ${n.supplier}` : ""}${
        n.category ? ` · ${n.category}` : ""
      } · knowledge: ${n.compositionKnowledge}`,
    };
  });
  return (
    <PickerList
      listId={listId}
      options={options}
      searching={search.length > 0}
      onPick={onPick}
    />
  );
}

/** Reference product search — name/supplier typeahead; the stored
 * composition status is shown so "unknown" stays visible. */
export function ReferenceProductPicker({
  label = "reference product",
  hint,
  onPick,
}: {
  label?: string;
  hint?: string;
  onPick: (p: Picked) => void;
}) {
  const listId = useId();
  const [term, setTerm] = useState("");
  const [picked, setPicked] = useState<Picked | null>(null);
  const search = useDebounced(term, 250);
  return (
    <PickerShell
      label={label}
      hint={hint ?? "search by product name or supplier"}
      term={term}
      onTerm={setTerm}
      picked={picked}
      onClear={() => setPicked(null)}
      listId={listId}
      expanded={!picked && search.length > 0}
    >
      <Suspense fallback={<p role="status">searching…</p>}>
        <ProductPickerResults
          listId={listId}
          search={search}
          onPick={(p) => {
            setPicked(p);
            onPick(p);
          }}
        />
      </Suspense>
    </PickerShell>
  );
}

/** Formulation revision search across families — baseline/candidate
 * selection by family name (§PAR-07: no uuid entry). */
export function FormulationRevisionPicker({
  label = "formulation revision",
  hint,
  statusFilter,
  onPick,
}: {
  label?: string;
  hint?: string;
  /** client-side status filter (e.g. only "accepted" for baselines) */
  statusFilter?: string;
  onPick: (p: Picked) => void;
}) {
  const listId = useId();
  const [term, setTerm] = useState("");
  const [picked, setPicked] = useState<Picked | null>(null);
  const search = useDebounced(term, 250);
  return (
    <PickerShell
      label={label}
      hint={hint ?? "search by family name"}
      term={term}
      onTerm={setTerm}
      picked={picked}
      onClear={() => setPicked(null)}
      listId={listId}
      expanded={!picked}
    >
      <Suspense fallback={<p role="status">searching…</p>}>
        <FilteredFormulationResults
          listId={listId}
          search={search}
          statusFilter={statusFilter}
          onPick={(p) => {
            setPicked(p);
            onPick(p);
          }}
        />
      </Suspense>
    </PickerShell>
  );
}

function FilteredFormulationResults({
  listId,
  search,
  statusFilter,
  onPick,
}: {
  listId: string;
  search: string;
  statusFilter?: string;
  onPick: (p: Picked) => void;
}) {
  const data = useLazyLoadQuery<registryFormulationRevisionsQuery>(
    RegistryFormulationRevisionsQuery,
    { familyId: null, search: search || null, first: 50 },
    { fetchPolicy: "network-only" },
  );
  const options = data.formulationRevisions.edges
    .map((e) => e.node)
    .filter((n) => (statusFilter ? n.status === statusFilter : true))
    .map((n) => {
      const ingredients = (n.payload as { ingredients?: unknown[] } | null)
        ?.ingredients;
      const count = Array.isArray(ingredients) ? ingredients.length : null;
      return {
        globalId: n.id,
        uuid: rawUuid(n.id),
        label: `${n.familyName ?? "formulation"} · rev ${n.revision} · ${n.status}${
          count != null ? ` · ${count} ingredients` : ""
        }`,
      };
    });
  return (
    <PickerList
      listId={listId}
      options={options}
      searching={search.length > 0}
      onPick={onPick}
    />
  );
}

/** Accepted candidate picker for experiment plans — binds the exact
 * accepted candidate revision (uuid) into the plan payload. */
export function CandidateRevisionPicker({
  taskId,
  label = "candidate revision",
  onPick,
}: {
  taskId: string;
  label?: string;
  onPick: (p: Picked) => void;
}) {
  const listId = useId();
  const [picked, setPicked] = useState<Picked | null>(null);
  const data = useLazyLoadQuery<candidatesRevisionPickerQuery>(
    CandidateRevisionPickerQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  const options = data.taskCandidateRevisions.edges
    .map((e) => e.node)
    .filter((n) => n.status === "accepted_for_research")
    .map((n) => ({
      globalId: n.id,
      uuid: rawUuid(n.id),
      label: `${n.entityKind} candidate rev ${n.revision}${
        n.hypothesis ? ` · ${n.hypothesis.slice(0, 60)}` : ""
      }`,
    }));
  return (
    <PickerShell
      label={label}
      hint="only candidates accepted for research are listed"
      term=""
      onTerm={() => {}}
      picked={picked}
      onClear={() => setPicked(null)}
      listId={listId}
      expanded={!picked && options.length > 0}
      readOnly
    >
      <PickerList
        listId={listId}
        options={options}
        searching
        onPick={(p) => {
          setPicked(p);
          onPick(p);
        }}
      />
    </PickerShell>
  );
}

/** Contract revision picker — plans bind the frozen contract the
 * experiment answers to. */
export function ContractRevisionPicker({
  taskId,
  label = "contract revision",
  onPick,
}: {
  taskId: string;
  label?: string;
  onPick: (p: Picked) => void;
}) {
  const listId = useId();
  const [picked, setPicked] = useState<Picked | null>(null);
  const data = useLazyLoadQuery<tasksContractRevisionsQuery>(
    ContractRevisionsQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  const options = data.taskContractRevisions.edges
    .map((e) => e.node)
    .filter((n) => n.status === "frozen" || n.status === "accepted")
    .map((n) => ({
      globalId: n.id,
      uuid: rawUuid(n.id),
      label: `contract rev ${n.revision} · ${n.status}`,
    }));
  return (
    <PickerShell
      label={label}
      hint="frozen contract revisions bind the plan to agreed criteria"
      term=""
      onTerm={() => {}}
      picked={picked}
      onClear={() => setPicked(null)}
      listId={listId}
      expanded={!picked && options.length > 0}
      readOnly
    >
      <PickerList
        listId={listId}
        options={options}
        searching
        onPick={(p) => {
          setPicked(p);
          onPick(p);
        }}
      />
    </PickerShell>
  );
}
