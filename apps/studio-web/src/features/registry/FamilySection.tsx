import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { InlineFinding } from "../../components/molecules/InlineFinding";
import { EmptyState, LoadingState } from "../../components/states/states";
import { rawUuid } from "../../relay/network";
import { FormulationEditor } from "./FormulationEditor";
import { RevisionDiff } from "./RevisionDiff";
import {
  RegistryFamiliesQuery,
  RegistryFormulationRevisionsQuery,
  RegistryProcessRevisionsQuery,
  RegistryFamilyCreateMutation,
  RegistryProcessAcceptMutation,
  RegistryProcessDraftMutation,
  RegistryRevisionAcceptMutation,
} from "./operations";

import type { registryFamiliesQuery } from "../../__generated__/registryFamiliesQuery.graphql";
import type { registryFamilyCreateMutation } from "../../__generated__/registryFamilyCreateMutation.graphql";
import type { registryFormulationRevisionsQuery } from "../../__generated__/registryFormulationRevisionsQuery.graphql";
import type { registryProcessAcceptMutation } from "../../__generated__/registryProcessAcceptMutation.graphql";
import type { registryProcessDraftMutation } from "../../__generated__/registryProcessDraftMutation.graphql";
import type { registryProcessRevisionsQuery } from "../../__generated__/registryProcessRevisionsQuery.graphql";
import type { registryRevisionAcceptMutation } from "../../__generated__/registryRevisionAcceptMutation.graphql";

type Errs = readonly {
  code: string;
  message: string;
  fieldPath?: string | null;
}[];

const STATUS_TONE: Record<
  string,
  "info" | "success" | "warning" | "danger" | "neutral"
> = {
  draft: "neutral",
  accepted: "success",
  frozen: "success",
  superseded: "warning",
  rejected: "danger",
};

function payloadSummary(payload: unknown): {
  ingredients: number | null;
  completeness: string | null;
  declaredTotal: string | null;
  findings: { code?: string; message?: string }[];
} {
  const p =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? (payload as Record<string, unknown>)
      : null;
  if (!p) {
    return { ingredients: null, completeness: null, declaredTotal: null, findings: [] };
  }
  const findings = Array.isArray(p.validationFindings)
    ? (p.validationFindings as { code?: string; message?: string }[])
    : [];
  return {
    ingredients: Array.isArray(p.ingredients) ? p.ingredients.length : null,
    completeness: p.completeness != null ? String(p.completeness) : null,
    declaredTotal: p.declaredTotal != null ? String(p.declaredTotal) : null,
    findings,
  };
}

function RevisionRow({
  node,
  onChanged,
}: {
  node: NonNullable<
    registryFormulationRevisionsQuery["response"]["formulationRevisions"]["edges"][number]["node"]
  >;
  onChanged: () => void;
}) {
  const [accept, pending] =
    useMutation<registryRevisionAcceptMutation>(RegistryRevisionAcceptMutation);
  const [diffOpen, setDiffOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const s = payloadSummary(node.payload);
  const uuid = rawUuid(node.id);
  return (
    <li className="cs-registry-row" data-revision-id={node.id}>
      <p>
        <strong>rev {node.revision}</strong>{" "}
        <Badge tone={STATUS_TONE[node.status] ?? "neutral"}>{node.status}</Badge>{" "}
        {s.ingredients != null && <small>{s.ingredients} ingredients</small>}{" "}
        {s.completeness && <small>completeness: {s.completeness}</small>}{" "}
        {s.declaredTotal && <small>declared total: {s.declaredTotal}</small>}{" "}
        {node.parentRevisionId && (
          <small>
            parent <code>{node.parentRevisionId.slice(0, 8)}…</code>
          </small>
        )}
      </p>
      {s.findings.map((f, i) => (
        <InlineFinding
          key={i}
          severity="warning"
          message={`${f.code ?? "finding"}: ${f.message ?? ""}`}
        />
      ))}
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      {node.status === "draft" && (
        <Button
          type="button"
          disabled={pending}
          onClick={() => {
            setError(null);
            accept({
              variables: { input: { revisionId: node.id } },
              onCompleted: (res) => {
                const errs = res.formulations.revisionAccept.errors;
                if (errs.length > 0) setError(errs[0].message);
                else onChanged();
              },
              onError: (e) => setError(e.message),
            });
          }}
        >
          accept revision
        </Button>
      )}
      <button
        type="button"
        onClick={() => setDiffOpen((o) => !o)}
        aria-expanded={diffOpen}
      >
        {diffOpen ? "hide diff" : "diff vs parent"}
      </button>
      {diffOpen && (
        <RevisionDiff
          baselineUuid={node.parentRevisionId ?? null}
          candidateUuid={uuid}
        />
      )}
    </li>
  );
}

function ProcessEditor({
  familyId,
  onSaved,
}: {
  familyId: string;
  onSaved: () => void;
}) {
  const [commit, pending] =
    useMutation<registryProcessDraftMutation>(RegistryProcessDraftMutation);
  const [steps, setSteps] = useState<{ key: number; action: string; detail: string }[]>([
    { key: 0, action: "", detail: "" },
  ]);
  const [nextKey, setNextKey] = useState(1);
  const [errors, setErrors] = useState<Errs>([]);
  const [saved, setSaved] = useState<string | null>(null);

  const save = () => {
    setErrors([]);
    setSaved(null);
    const payload = {
      steps: steps
        .filter((s) => s.action.trim())
        .map((s, i) => ({
          order: i + 1,
          action: s.action.trim(),
          ...(s.detail.trim() ? { notes: s.detail.trim() } : {}),
        })),
    };
    commit({
      variables: {
        input: {
          familyId,
          payload,
          idempotencyKey: `fw-process-${crypto.randomUUID()}`,
        },
      },
      onCompleted: (resp) => {
        const errs = resp.formulations.processDraft.errors ?? [];
        if (errs.length > 0) {
          setErrors(errs);
          return;
        }
        setSaved("process draft saved");
        setSteps([{ key: 0, action: "", detail: "" }]);
        setNextKey(1);
        onSaved();
      },
      onError: (e) =>
        setErrors([{ code: "NETWORK", message: `not saved: ${e.message}` }]),
    });
  };

  return (
    <form
      aria-label="new process revision"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <h4>new process revision</h4>
      <p className="cs-field__hint">step order is content — it changes the signature</p>
      <ol>
        {steps.map((s) => (
          <li key={s.key}>
            <TextField
              label={`step ${s.key + 1} action`}
              value={s.action}
              onChange={(e) =>
                setSteps((ss) =>
                  ss.map((x) =>
                    x.key === s.key ? { ...x, action: e.target.value } : x,
                  ),
                )
              }
              required
            />
            <TextField
              label="notes (optional)"
              value={s.detail}
              onChange={(e) =>
                setSteps((ss) =>
                  ss.map((x) =>
                    x.key === s.key ? { ...x, detail: e.target.value } : x,
                  ),
                )
              }
            />
            <Button
              variant="ghost"
              onClick={() =>
                setSteps((ss) =>
                  ss.length > 1 ? ss.filter((x) => x.key !== s.key) : ss,
                )
              }
            >
              remove step
            </Button>
          </li>
        ))}
      </ol>
      <Button
        type="button"
        onClick={() => {
          setSteps((ss) => [...ss, { key: nextKey, action: "", detail: "" }]);
          setNextKey((k) => k + 1);
        }}
      >
        add step
      </Button>
      {errors.map((e, i) => (
        <InlineFinding
          key={`${e.code}:${i}`}
          severity="error"
          message={`${e.fieldPath ? `${e.fieldPath}: ` : ""}${e.message}`}
        />
      ))}
      {saved && <p role="status">{saved}</p>}
      <Button variant="primary" type="submit" disabled={pending}>
        save process draft
      </Button>
    </form>
  );
}

function ProcessRevisionList({
  familyId,
  fetchKey,
}: {
  familyId: string;
  fetchKey: number;
}) {
  const [accept, accepting] =
    useMutation<registryProcessAcceptMutation>(RegistryProcessAcceptMutation);
  const [error, setError] = useState<string | null>(null);
  const [localKey, setLocalKey] = useState(0);
  const data = useLazyLoadQuery<registryProcessRevisionsQuery>(
    RegistryProcessRevisionsQuery,
    { familyId, first: 20 },
    { fetchKey: fetchKey + localKey, fetchPolicy: "network-only" },
  );
  const nodes = data.processRevisions.edges.map((e) => e.node);
  if (nodes.length === 0) {
    return <EmptyState title="no process revisions yet" />;
  }
  return (
    <ul aria-label="process revisions">
      {nodes.map((n) => {
        const p = (n.payload ?? {}) as { steps?: unknown[] };
        const count = Array.isArray(p.steps) ? p.steps.length : null;
        return (
          <li key={n.id}>
            <code>rev {n.revision}</code>{" "}
            <Badge tone={STATUS_TONE[n.status] ?? "neutral"}>{n.status}</Badge>{" "}
            {count != null && <small>{count} steps</small>}{" "}
            {n.status === "draft" && (
              <Button
                type="button"
                disabled={accepting}
                onClick={() => {
                  setError(null);
                  accept({
                    variables: { input: { revisionId: n.id } },
                    onCompleted: (res) => {
                      const errs = res.formulations.processAccept.errors;
                      if (errs.length > 0) setError(errs[0].message);
                      else setLocalKey((k) => k + 1);
                    },
                    onError: (e) => setError(e.message),
                  });
                }}
              >
                accept process revision
              </Button>
            )}
          </li>
        );
      })}
      {error && (
        <li role="alert" className="cs-field__error">
          {error}
        </li>
      )}
    </ul>
  );
}

type FamilyNode =
  registryFamiliesQuery["response"]["formulationFamilies"]["edges"][number]["node"];

function FamilyDetail({ family }: { family: FamilyNode }) {
  const [fetchKey, setFetchKey] = useState(0);
  const [editorOpen, setEditorOpen] = useState(false);
  const [processEditorOpen, setProcessEditorOpen] = useState(false);
  const bump = () => setFetchKey((k) => k + 1);
  const data = useLazyLoadQuery<registryFormulationRevisionsQuery>(
    RegistryFormulationRevisionsQuery,
    { familyId: family.id, first: 50 },
    { fetchKey, fetchPolicy: "network-only" },
  );
  const nodes = data.formulationRevisions.edges.map((e) => e.node);
  const latestAccepted = nodes
    .filter((n) => n.status === "accepted")
    .sort((a, b) => b.revision - a.revision)[0];
  return (
    <section aria-label={`family ${family.name}`}>
      <h3>{family.name}</h3>
      {family.description && <p>{family.description}</p>}
      {nodes.length === 0 ? (
        <EmptyState title="no formulation revisions yet — draft one below" />
      ) : (
        <ul aria-label="formulation revisions">
          {nodes.map((n) => (
            <RevisionRow key={n.id} node={n} onChanged={bump} />
          ))}
        </ul>
      )}
      <Button type="button" onClick={() => setEditorOpen((o) => !o)}>
        {editorOpen ? "close formulation editor" : "new formulation revision"}
      </Button>{" "}
      <Button type="button" onClick={() => setProcessEditorOpen((o) => !o)}>
        {processEditorOpen ? "close process editor" : "new process revision"}
      </Button>
      {editorOpen && (
        <FormulationEditor
          familyId={family.id}
          parentRevisionId={
            latestAccepted ? rawUuid(latestAccepted.id) : undefined
          }
          parentPayload={latestAccepted?.payload}
          onSaved={bump}
        />
      )}
      {processEditorOpen && (
        <ProcessEditor familyId={family.id} onSaved={bump} />
      )}
      <h4>process revisions</h4>
      <Suspense fallback={<LoadingState label="loading process revisions…" />}>
        <ProcessRevisionList familyId={family.id} fetchKey={fetchKey} />
      </Suspense>
    </section>
  );
}

function FamilyCreateForm({ onCreated }: { onCreated: () => void }) {
  const [commit, pending] =
    useMutation<registryFamilyCreateMutation>(RegistryFamilyCreateMutation);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [errors, setErrors] = useState<Errs>([]);
  return (
    <form
      aria-label="create formulation family"
      onSubmit={(e) => {
        e.preventDefault();
        setErrors([]);
        commit({
          variables: {
            input: {
              name,
              description: description || undefined,
              idempotencyKey: `fw-family-${crypto.randomUUID()}`,
            },
          },
          onCompleted: (resp) => {
            const errs = resp.formulations.familyCreate.errors;
            if (errs.length > 0) {
              setErrors(errs);
              return;
            }
            setName("");
            setDescription("");
            onCreated();
          },
          onError: (e) =>
            setErrors([
              { code: "NETWORK", message: `not saved: ${e.message}` },
            ]),
        });
      }}
    >
      <h3>create formulation family</h3>
      <TextField
        label="family name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <TextField
        label="description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      {errors.map((e, i) => (
        <InlineFinding
          key={`${e.code}:${i}`}
          severity="error"
          message={`${e.fieldPath ? `${e.fieldPath}: ` : ""}${e.message}`}
        />
      ))}
      <Button variant="primary" type="submit" disabled={pending || !name.trim()}>
        create family
      </Button>
    </form>
  );
}

function FamilyList({
  search,
  fetchKey,
  selectedId,
  onSelect,
}: {
  search: string;
  fetchKey: number;
  selectedId: string | null;
  onSelect: (f: FamilyNode) => void;
}) {
  const data = useLazyLoadQuery<registryFamiliesQuery>(
    RegistryFamiliesQuery,
    { search: search || null, first: 50 },
    { fetchKey, fetchPolicy: "network-only" },
  );
  const nodes = data.formulationFamilies.edges.map((e) => e.node);
  if (nodes.length === 0) {
    return <EmptyState title="no formulation families match" />;
  }
  return (
    <ul aria-label="formulation families">
      {nodes.map((n) => (
        <li key={n.id}>
          <button
            type="button"
            aria-pressed={selectedId === n.id}
            onClick={() => onSelect(n)}
          >
            <strong>{n.name}</strong>
          </button>{" "}
          {n.description && <small>{n.description}</small>}
        </li>
      ))}
    </ul>
  );
}

/** Formulation families + revisions + process revisions (§5, PAR-07):
 * a family carries versioned formulation payloads with lineage —
 * drafts may be incomplete, acceptance is the gate. */
export function FormulationFamiliesSection() {
  const [search, setSearch] = useState("");
  const [fetchKey, setFetchKey] = useState(0);
  const [selected, setSelected] = useState<FamilyNode | null>(null);
  return (
    <section aria-label="formulation families">
      <TextField
        label="search families by name"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        role="searchbox"
        autoComplete="off"
      />
      <Suspense fallback={<LoadingState label="loading families…" />}>
        <FamilyList
          search={search}
          fetchKey={fetchKey}
          selectedId={selected?.id ?? null}
          onSelect={setSelected}
        />
      </Suspense>
      <FamilyCreateForm onCreated={() => setFetchKey((k) => k + 1)} />
      {selected && <FamilyDetail key={selected.id} family={selected} />}
    </section>
  );
}
