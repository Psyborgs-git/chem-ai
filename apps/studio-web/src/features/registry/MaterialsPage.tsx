import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { DecimalField } from "../../components/atoms/DecimalField";
import { TextField } from "../../components/atoms/TextField";
import { UnitSelect } from "../../components/atoms/UnitSelect";
import { InlineFinding } from "../../components/molecules/InlineFinding";
import { EmptyState, LoadingState } from "../../components/states/states";
import {
  GradeCreateMutation,
  IdentityCreateMutation,
  ReferenceProductCreateMutation,
  ReferenceRevisionDraftMutation,
  ReferenceRevisionFreezeMutation,
  StructureReviewMutation,
} from "../materials/operations";
import { MaterialIdentityPicker } from "./pickers";
import {
  RegistryGradesQuery,
  RegistryIdentitiesQuery,
  RegistryProductRevisionsQuery,
  RegistryProductsQuery,
} from "./operations";
import { FormulationFamiliesSection } from "./FamilySection";

import type { materialsGradeCreateMutation } from "../../__generated__/materialsGradeCreateMutation.graphql";
import type { materialsIdentityCreateMutation } from "../../__generated__/materialsIdentityCreateMutation.graphql";
import type { materialsRefRevDraftMutation } from "../../__generated__/materialsRefRevDraftMutation.graphql";
import type { materialsRefRevFreezeMutation } from "../../__generated__/materialsRefRevFreezeMutation.graphql";
import type { materialsReferenceCreateMutation } from "../../__generated__/materialsReferenceCreateMutation.graphql";
import type { materialsStructureReviewMutation } from "../../__generated__/materialsStructureReviewMutation.graphql";
import type { registryGradesQuery } from "../../__generated__/registryGradesQuery.graphql";
import type { registryIdentitiesQuery } from "../../__generated__/registryIdentitiesQuery.graphql";
import type { registryProductRevisionsQuery } from "../../__generated__/registryProductRevisionsQuery.graphql";
import type { registryProductsQuery } from "../../__generated__/registryProductsQuery.graphql";

const SECTIONS = [
  { key: "identities", label: "material identities" },
  { key: "grades", label: "material grades" },
  { key: "products", label: "reference products" },
  { key: "formulations", label: "formulation families" },
] as const;

type SectionKey = (typeof SECTIONS)[number]["key"];

const MATERIAL_KINDS = [
  "defined_molecule",
  "polymer",
  "commercial_mixture",
  "substance_class",
  "unknown",
] as const;

const CONFIDENTIALITY = ["public", "internal", "confidential"] as const;
const COMPOSITION_KNOWLEDGE = ["known", "partial", "unknown"] as const;
const ACTIVE_UNITS = ["mass_percent", "mass_fraction", "mass"] as const;

type Errs = readonly { code: string; message: string; fieldPath?: string | null }[];

function ErrorList({ errors }: { errors: Errs }) {
  return (
    <>
      {errors.map((e, i) => (
        <InlineFinding
          key={`${e.code}:${e.fieldPath ?? ""}:${i}`}
          severity="error"
          message={`${e.fieldPath ? `${e.fieldPath}: ` : ""}${e.message}`}
        />
      ))}
    </>
  );
}

function SearchField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <TextField
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      role="searchbox"
      autoComplete="off"
    />
  );
}

function IdentityRow({
  node,
  onReviewed,
}: {
  node: {
    id: string;
    name: string;
    kind: string;
    structureStatus: string;
    evidenceStatus: string;
    identifiers: unknown;
  };
  onReviewed: () => void;
}) {
  const [review, pending] =
    useMutation<materialsStructureReviewMutation>(StructureReviewMutation);
  const [error, setError] = useState<string | null>(null);
  const ids =
    (node.identifiers as
      | readonly { scheme?: string; value?: string }[]
      | null) ?? [];
  return (
    <li className="cs-registry-row">
      <span>
        <strong>{node.name}</strong> <small>{node.kind}</small>
      </span>{" "}
      <Badge tone="neutral">{node.structureStatus}</Badge>{" "}
      <Badge tone="info">evidence: {node.evidenceStatus}</Badge>{" "}
      {ids.map((i, idx) => (
        <code key={idx}>
          {i.scheme}:{i.value}
        </code>
      ))}
      {node.structureStatus === "unreviewed" && (
        <Button
          type="button"
          disabled={pending}
          onClick={() => {
            setError(null);
            review({
              variables: { input: { identityId: node.id } },
              onCompleted: (res) => {
                const errs = res.materials.structureReview.errors;
                if (errs.length > 0) {
                  setError(errs[0].message);
                } else {
                  onReviewed();
                }
              },
              onError: (e) => setError(e.message),
            });
          }}
        >
          mark structure reviewed
        </Button>
      )}
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
    </li>
  );
}

function IdentityCreateForm({ onCreated }: { onCreated: () => void }) {
  const [commit, pending] =
    useMutation<materialsIdentityCreateMutation>(IdentityCreateMutation);
  const [kind, setKind] = useState<string>(MATERIAL_KINDS[0]);
  const [name, setName] = useState("");
  const [scheme, setScheme] = useState("");
  const [idValue, setIdValue] = useState("");
  const [structure, setStructure] = useState("");
  const [confidentiality, setConfidentiality] = useState("internal");
  const [errors, setErrors] = useState<Errs>([]);

  const submit = () => {
    setErrors([]);
    commit({
      variables: {
        input: {
          kind,
          name,
          identifiers:
            scheme && idValue ? [{ scheme, value: idValue }] : null,
          structure: structure || undefined,
          structureFormat: structure ? "smiles" : undefined,
          confidentiality,
          idempotencyKey: `fw-identity-${crypto.randomUUID()}`,
        },
      },
      onCompleted: (resp) => {
        const errs = resp.materials.identityCreate.errors;
        if (errs.length > 0) {
          setErrors(errs);
          return;
        }
        setName("");
        setScheme("");
        setIdValue("");
        setStructure("");
        onCreated();
      },
      onError: (e) =>
        setErrors([{ code: "NETWORK", message: `not saved: ${e.message}` }]),
    });
  };

  return (
    <form
      aria-label="register material identity"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <h3>register material identity</h3>
      <div className="cs-field">
        <label className="cs-field__label" htmlFor="id-kind">
          kind
        </label>
        <select
          id="id-kind"
          className="cs-select"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          {MATERIAL_KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </div>
      <TextField
        label="name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <fieldset>
        <legend>identifier (optional)</legend>
        <TextField
          label="scheme (e.g. cas, inchikey)"
          value={scheme}
          onChange={(e) => setScheme(e.target.value)}
        />
        <TextField
          label="value"
          value={idValue}
          onChange={(e) => setIdValue(e.target.value)}
        />
      </fieldset>
      <TextField
        label="structure (optional)"
        hint="SMILES/InChI — structure lands unreviewed until a scientist reviews it"
        value={structure}
        onChange={(e) => setStructure(e.target.value)}
      />
      <div className="cs-field">
        <label className="cs-field__label" htmlFor="id-conf">
          confidentiality
        </label>
        <select
          id="id-conf"
          className="cs-select"
          value={confidentiality}
          onChange={(e) => setConfidentiality(e.target.value)}
        >
          {CONFIDENTIALITY.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
      <ErrorList errors={errors} />
      <Button variant="primary" type="submit" disabled={pending || !name.trim()}>
        register identity
      </Button>
    </form>
  );
}

function IdentitiesSection() {
  const [search, setSearch] = useState("");
  const [fetchKey, setFetchKey] = useState(0);
  return (
    <section aria-label="material identities">
      <SearchField
        label="search identities by name or identifier"
        value={search}
        onChange={setSearch}
      />
      <Suspense fallback={<LoadingState label="loading identities…" />}>
        <IdentityList
          search={search}
          fetchKey={fetchKey}
          onReviewed={() => setFetchKey((k) => k + 1)}
        />
      </Suspense>
      <IdentityCreateForm onCreated={() => setFetchKey((k) => k + 1)} />
    </section>
  );
}

function IdentityList({
  search,
  fetchKey,
  onReviewed,
}: {
  search: string;
  fetchKey: number;
  onReviewed: () => void;
}) {
  const data = useLazyLoadQuery<registryIdentitiesQuery>(
    RegistryIdentitiesQuery,
    { search: search || null, first: 50 },
    { fetchKey, fetchPolicy: "network-only" },
  );
  const nodes = data.materialIdentities.edges.map((e) => e.node);
  if (nodes.length === 0) {
    return <EmptyState title="no material identities match" />;
  }
  return (
    <ul aria-label="material identities">
      {nodes.map((n) => (
        <IdentityRow key={n.id} node={n} onReviewed={onReviewed} />
      ))}
    </ul>
  );
}

function GradeCreateForm({ onCreated }: { onCreated: () => void }) {
  const [commit, pending] =
    useMutation<materialsGradeCreateMutation>(GradeCreateMutation);
  const [material, setMaterial] = useState<{
    globalId: string;
    label: string;
  } | null>(null);
  const [supplier, setSupplier] = useState("");
  const [gradeName, setGradeName] = useState("");
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState<string>("mass_percent");
  const [basis, setBasis] = useState("as_supplied");
  const [errors, setErrors] = useState<Errs>([]);

  const submit = () => {
    setErrors([]);
    commit({
      variables: {
        input: {
          materialId: material?.globalId ?? "",
          supplier,
          gradeName,
          activeContent: value
            ? { value, unit, basis }
            : null,
          idempotencyKey: `fw-grade-${crypto.randomUUID()}`,
        },
      },
      onCompleted: (resp) => {
        const errs = resp.materials.gradeCreate.errors;
        if (errs.length > 0) {
          setErrors(errs);
          return;
        }
        setMaterial(null);
        setSupplier("");
        setGradeName("");
        setValue("");
        onCreated();
      },
      onError: (e) =>
        setErrors([{ code: "NETWORK", message: `not saved: ${e.message}` }]),
    });
  };

  return (
    <form
      aria-label="register material grade"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <h3>register material grade</h3>
      <MaterialIdentityPicker
        label="material"
        hint="search the registry by name or identifier"
        onPick={(p) => setMaterial({ globalId: p.globalId, label: p.label })}
      />
      <TextField
        label="supplier"
        value={supplier}
        onChange={(e) => setSupplier(e.target.value)}
        required
      />
      <TextField
        label="grade name"
        value={gradeName}
        onChange={(e) => setGradeName(e.target.value)}
        required
      />
      <fieldset>
        <legend>active content (optional)</legend>
        <DecimalField
          label="value"
          value={value}
          onValueChange={setValue}
        />
        <UnitSelect
          label="unit"
          units={ACTIVE_UNITS}
          value={unit}
          onValueChange={setUnit}
        />
        <div className="cs-field">
          <label className="cs-field__label" htmlFor="grade-basis">
            basis
          </label>
          <select
            id="grade-basis"
            className="cs-select"
            value={basis}
            onChange={(e) => setBasis(e.target.value)}
          >
            <option value="as_supplied">as_supplied</option>
            <option value="active_solids">active_solids</option>
          </select>
        </div>
      </fieldset>
      <ErrorList errors={errors} />
      <Button
        variant="primary"
        type="submit"
        disabled={pending || !material || !supplier.trim() || !gradeName.trim()}
      >
        register grade
      </Button>
    </form>
  );
}

function GradeList({
  search,
  fetchKey,
}: {
  search: string;
  fetchKey: number;
}) {
  const data = useLazyLoadQuery<registryGradesQuery>(
    RegistryGradesQuery,
    { search: search || null, first: 50 },
    { fetchKey, fetchPolicy: "network-only" },
  );
  const nodes = data.materialGrades.edges.map((e) => e.node);
  if (nodes.length === 0) {
    return <EmptyState title="no material grades match" />;
  }
  return (
    <ul aria-label="material grades">
      {nodes.map((n) => (
        <li key={n.id} className="cs-registry-row">
          <span>
            <strong>{n.gradeName}</strong> <small>{n.supplier}</small>
          </span>{" "}
          {n.activeContent != null && (
            <small>
              active: {JSON.stringify(n.activeContent)}
            </small>
          )}{" "}
          {n.reconciledInto && <Badge tone="warning">reconciled</Badge>}
        </li>
      ))}
    </ul>
  );
}

function GradesSection() {
  const [search, setSearch] = useState("");
  const [fetchKey, setFetchKey] = useState(0);
  return (
    <section aria-label="material grades">
      <SearchField
        label="search grades by name or supplier"
        value={search}
        onChange={setSearch}
      />
      <Suspense fallback={<LoadingState label="loading grades…" />}>
        <GradeList search={search} fetchKey={fetchKey} />
      </Suspense>
      <GradeCreateForm onCreated={() => setFetchKey((k) => k + 1)} />
    </section>
  );
}

function ProductCreateForm({ onCreated }: { onCreated: () => void }) {
  const [commit, pending] =
    useMutation<materialsReferenceCreateMutation>(ReferenceProductCreateMutation);
  const [name, setName] = useState("");
  const [supplier, setSupplier] = useState("");
  const [category, setCategory] = useState("");
  const [knowledge, setKnowledge] = useState<string>("unknown");
  const [errors, setErrors] = useState<Errs>([]);

  const submit = () => {
    setErrors([]);
    commit({
      variables: {
        input: {
          name,
          supplier: supplier || undefined,
          category: category || undefined,
          compositionKnowledge: knowledge,
          idempotencyKey: `fw-product-${crypto.randomUUID()}`,
        },
      },
      onCompleted: (resp) => {
        const errs = resp.materials.referenceProductCreate.errors;
        if (errs.length > 0) {
          setErrors(errs);
          return;
        }
        setName("");
        setSupplier("");
        setCategory("");
        onCreated();
      },
      onError: (e) =>
        setErrors([{ code: "NETWORK", message: `not saved: ${e.message}` }]),
    });
  };

  return (
    <form
      aria-label="register reference product"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <h3>register reference product</h3>
      <TextField
        label="product name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <TextField
        label="supplier (optional)"
        value={supplier}
        onChange={(e) => setSupplier(e.target.value)}
      />
      <TextField
        label="category (optional)"
        value={category}
        onChange={(e) => setCategory(e.target.value)}
      />
      <div className="cs-field">
        <label className="cs-field__label" htmlFor="prod-knowledge">
          composition knowledge
        </label>
        <select
          id="prod-knowledge"
          className="cs-select"
          value={knowledge}
          onChange={(e) => setKnowledge(e.target.value)}
        >
          {COMPOSITION_KNOWLEDGE.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <p className="cs-field__hint">
          unknown stays unknown — no recovered composition is claimed
        </p>
      </div>
      <ErrorList errors={errors} />
      <Button variant="primary" type="submit" disabled={pending || !name.trim()}>
        register product
      </Button>
    </form>
  );
}

type ProductNode =
  registryProductsQuery["response"]["referenceProducts"]["edges"][number]["node"];

function ProductRevisionDraftForm({
  productId,
  onDone,
}: {
  productId: string;
  onDone: () => void;
}) {
  const [commit, pending] =
    useMutation<materialsRefRevDraftMutation>(ReferenceRevisionDraftMutation);
  const [knowledge, setKnowledge] = useState<string>("partial");
  const [claimed, setClaimed] = useState("");
  const [errors, setErrors] = useState<Errs>([]);
  return (
    <form
      aria-label="draft product revision"
      onSubmit={(e) => {
        e.preventDefault();
        setErrors([]);
        commit({
          variables: {
            input: {
              productId,
              payload: {
                compositionKnowledge: knowledge,
                ...(claimed
                  ? { claimedComposition: claimed }
                  : {}),
              },
              idempotencyKey: `fw-rrev-${crypto.randomUUID()}`,
            },
          },
          onCompleted: (resp) => {
            const errs = resp.materials.referenceRevisionDraft.errors;
            if (errs.length > 0) {
              setErrors(errs);
              return;
            }
            setClaimed("");
            onDone();
          },
          onError: (e) =>
            setErrors([
              { code: "NETWORK", message: `not saved: ${e.message}` },
            ]),
        });
      }}
    >
      <div className="cs-field">
        <label className="cs-field__label" htmlFor={`rev-k-${productId}`}>
          composition knowledge
        </label>
        <select
          id={`rev-k-${productId}`}
          className="cs-select"
          value={knowledge}
          onChange={(e) => setKnowledge(e.target.value)}
        >
          {COMPOSITION_KNOWLEDGE.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </div>
      <TextField
        label="claimed composition (as stated by the source)"
        hint="recorded verbatim — ambiguous fields stay proposed, never normalized"
        value={claimed}
        onChange={(e) => setClaimed(e.target.value)}
      />
      <ErrorList errors={errors} />
      <Button type="submit" disabled={pending}>
        save draft revision
      </Button>
    </form>
  );
}

function ProductRevisionList({
  productId,
  fetchKey,
}: {
  productId: string;
  fetchKey: number;
}) {
  const [localKey, setLocalKey] = useState(0);
  const data = useLazyLoadQuery<registryProductRevisionsQuery>(
    RegistryProductRevisionsQuery,
    { productId, first: 20 },
    { fetchKey: fetchKey + localKey, fetchPolicy: "network-only" },
  );
  const [freeze, freezing] =
    useMutation<materialsRefRevFreezeMutation>(ReferenceRevisionFreezeMutation);
  const [error, setError] = useState<string | null>(null);
  const nodes = data.referenceProductRevisions.edges.map((e) => e.node);
  return (
    <div>
      {nodes.length === 0 ? (
        <EmptyState title="no revisions yet" />
      ) : (
        <ul aria-label="product revisions">
          {nodes.map((n) => {
            const p = (n.payload ?? {}) as Record<string, unknown>;
            return (
              <li key={n.id}>
                <code>rev {n.revision}</code>{" "}
                <Badge
                  tone={n.status === "frozen" ? "success" : "neutral"}
                >
                  {n.status}
                </Badge>{" "}
                <small>
                  knowledge: {String(p.compositionKnowledge ?? "—")}
                </small>{" "}
                {n.status === "draft" && (
                  <Button
                    type="button"
                    disabled={freezing}
                    onClick={() => {
                      setError(null);
                      freeze({
                        variables: {
                          input: { revisionId: n.id },
                        },
                        onCompleted: (res) => {
                          const errs =
                            res.materials.referenceRevisionFreeze.errors;
                          if (errs.length > 0) setError(errs[0].message);
                          else setLocalKey((k) => k + 1);
                        },
                        onError: (e) => setError(e.message),
                      });
                    }}
                  >
                    freeze
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      <ProductRevisionDraftForm
        productId={productId}
        onDone={() => setLocalKey((k) => k + 1)}
      />
    </div>
  );
}

function ProductRow({ product, fetchKey }: { product: ProductNode; fetchKey: number }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="cs-registry-row">
      <span>
        <strong>{product.name}</strong>{" "}
        <small>
          {product.supplier ?? ""}
          {product.category ? ` · ${product.category}` : ""}
        </small>
      </span>{" "}
      <Badge
        tone={
          product.compositionKnowledge === "unknown"
            ? "warning"
            : product.compositionKnowledge === "partial"
              ? "info"
              : "success"
        }
      >
        composition: {product.compositionKnowledge}
      </Badge>{" "}
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? "hide revisions" : "revisions"}
      </button>
      {open && (
        <Suspense fallback={<LoadingState label="loading revisions…" />}>
          <ProductRevisionList productId={product.id} fetchKey={fetchKey} />
        </Suspense>
      )}
    </li>
  );
}

function ProductList({
  search,
  fetchKey,
}: {
  search: string;
  fetchKey: number;
}) {
  const data = useLazyLoadQuery<registryProductsQuery>(
    RegistryProductsQuery,
    { search: search || null, first: 50 },
    { fetchKey, fetchPolicy: "network-only" },
  );
  const nodes = data.referenceProducts.edges.map((e) => e.node);
  if (nodes.length === 0) {
    return <EmptyState title="no reference products match" />;
  }
  return (
    <ul aria-label="reference products">
      {nodes.map((n) => (
        <ProductRow key={n.id} product={n} fetchKey={fetchKey} />
      ))}
    </ul>
  );
}

function ProductsSection() {
  const [search, setSearch] = useState("");
  const [fetchKey, setFetchKey] = useState(0);
  return (
    <section aria-label="reference products">
      <SearchField
        label="search products by name or supplier"
        value={search}
        onChange={setSearch}
      />
      <Suspense fallback={<LoadingState label="loading products…" />}>
        <ProductList search={search} fetchKey={fetchKey} />
      </Suspense>
      <ProductCreateForm onCreated={() => setFetchKey((k) => k + 1)} />
    </section>
  );
}

/** Materials & Products registry (§6.1, PAR-07): the real surface the
 * nav link was removed for lacking — identities, grades, reference
 * products and formulation families, all backed by live queries. */
export function MaterialsPage() {
  const [section, setSection] = useState<SectionKey>("identities");
  return (
    <div>
      <h1>Materials &amp; Products</h1>
      <p>
        The canonical registry. Identities resolve by name or identifier —
        raw ids are never the working path.
      </p>
      <nav aria-label="registry sections">
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            type="button"
            aria-pressed={section === s.key}
            className={
              section === s.key ? "cs-section-nav is-active" : "cs-section-nav"
            }
            onClick={() => setSection(s.key)}
          >
            {s.label}
          </button>
        ))}
      </nav>
      {section === "identities" && <IdentitiesSection />}
      {section === "grades" && <GradesSection />}
      {section === "products" && <ProductsSection />}
      {section === "formulations" && <FormulationFamiliesSection />}
    </div>
  );
}
