/** Evidence panel (CS-0302, §10): claims grouped by kind — document
 * claims, inferred suggestions and measured outcomes stay visibly
 * distinct. Contradiction links keep both sides on screen. */
import { Suspense, useState } from "react";
import { PageHeader, StructuredData, TechnicalDetails } from "../../components/layout/StudioLayout";
import { Link } from "react-router";
import { useLazyLoadQuery, useMutation, usePaginationFragment } from "react-relay";

import {
  Badge,
  Button,
  EmptyState,
  EvidenceTypeLabel,
  LoadingState,
  SourceCitation,
} from "../../components";
import { PaginationControls } from "../../components/molecules/PaginationControls";
import type { evidenceClaimsQuery } from "../../__generated__/evidenceClaimsQuery.graphql";
import type { evidenceClaimsPaginationQuery } from "../../__generated__/evidenceClaimsPaginationQuery.graphql";
import type { evidenceClaimLinksQuery } from "../../__generated__/evidenceClaimLinksQuery.graphql";
import type { evidenceClaimReviewMutation } from "../../__generated__/evidenceClaimReviewMutation.graphql";
import type { EvidencePanel_claims$key, EvidencePanel_claims$data } from "../../__generated__/EvidencePanel_claims.graphql";
import {
  ClaimLinksQuery,
  ClaimReviewMutation,
  ClaimsFragment,
  EvidenceClaimsQuery,
} from "./operations";

const KIND_LABEL: Record<string, string> = {
  document_claim: "document claim",
  inferred_suggestion: "inferred suggestion",
  measured_outcome: "measured outcome",
};

const KIND_EVIDENCE: Record<string, "imported" | "computed" | "measured"> = {
  document_claim: "imported",
  inferred_suggestion: "computed",
  measured_outcome: "measured",
};

function locatorText(locator: unknown): string | undefined {
  if (locator && typeof locator === "object") {
    const l = locator as Record<string, unknown>;
    if (l.sheet && l.cell) return `${String(l.sheet)}!${String(l.cell)}`;
    if (l.page) return `page ${String(l.page)}`;
    if (l.jsonpath) return String(l.jsonpath);
    if (l.row !== undefined && l.col !== undefined)
      return `row ${String(l.row)}, col ${String(l.col)}`;
    if (l.paragraph !== undefined) return `paragraph ${String(l.paragraph)}`;
    return JSON.stringify(locator);
  }
  return undefined;
}

type ClaimNode = NonNullable<
  EvidencePanel_claims$data["evidenceClaims"]["edges"][number]["node"]
>;

function ClaimLinks({ claimId }: { claimId: string }) {
  const data = useLazyLoadQuery<evidenceClaimLinksQuery>(ClaimLinksQuery, {
    claimId,
  });
  const links = data.claimLinks;
  if (links.length === 0) return null;
  return (
    <ul aria-label="claim relations">
      {links.map((l, i) => (
        <li key={i}>
          <Badge tone={l.relation === "contradicts" ? "danger" : "info"}>
            {l.relation}
          </Badge>{" "}
          {l.fromClaimId === claimId ? l.toClaimId : l.fromClaimId}
          {l.note ? ` — ${l.note}` : ""}
        </li>
      ))}
    </ul>
  );
}

function ClaimCard({ claim }: { claim: ClaimNode }) {
  const [review, inFlight] =
    useMutation<evidenceClaimReviewMutation>(ClaimReviewMutation);
  const [error, setError] = useState<string | null>(null);
  return (
    <article className="cs-evidence-card" data-claim-id={claim.id} data-status={claim.status}>
      <header className="cs-evidence-card__header">
        <EvidenceTypeLabel kind={KIND_EVIDENCE[claim.kind] ?? "unknown"} />{" "}
        <strong>{KIND_LABEL[claim.kind] ?? claim.kind}</strong>{" "}
        <Badge
          tone={
            claim.status === "accepted"
              ? "success"
              : claim.status === "rejected"
                ? "danger"
                : "neutral"
          }
        >
          {claim.status}
        </Badge>
      </header>
      <div className="cs-evidence-card__body"><section><h3>Subject</h3><StructuredData value={claim.subject} /></section><section><h3>Statement</h3><StructuredData value={claim.statement} /></section></div>
      {claim.locator && (
        /* AT-0302-3: citation surfaces the exact page/cell locator */
        <SourceCitation
          sourceId={claim.id}
          title={locatorText(claim.locator) ?? "source"}
          kind="import"
          locator={claim.originalText ?? undefined}
        />
      )}
      {claim.conditions && (
        <section><h3>Conditions</h3><StructuredData value={claim.conditions} /></section>
      )}
      {claim.status === "proposed" && (
        <p>
          <Button
            disabled={inFlight}
            onClick={() =>
              review({
                variables: {
                  input: { claimId: claim.id, decision: "accepted" },
                },
                onError: (e) => setError(e.message),
              })
            }
          >
            accept claim
          </Button>{" "}
          <Button
            disabled={inFlight}
            onClick={() =>
              review({
                variables: {
                  input: { claimId: claim.id, decision: "rejected" },
                },
                onError: (e) => setError(e.message),
              })
            }
          >
            reject claim
          </Button>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <Suspense fallback={null}>
        <ClaimLinks claimId={claim.id} />
      </Suspense>
      <TechnicalDetails value={{ subject: claim.subject, statement: claim.statement, conditions: claim.conditions }} label="Inspect exact claim data" />
    </article>
  );
}

function Claims() {
  const query = useLazyLoadQuery<evidenceClaimsQuery>(EvidenceClaimsQuery, {});
  const { data, loadNext, hasNext, isLoadingNext } = usePaginationFragment<
    evidenceClaimsPaginationQuery,
    EvidencePanel_claims$key
  >(ClaimsFragment, query);
  const [loadError, setLoadError] = useState<string | null>(null);
  const claims = data.evidenceClaims.edges.map((e) => e.node);
  const loadNextPage = () => {
    setLoadError(null);
    loadNext(20, {
      onComplete: (e) => {
        if (e) setLoadError(e.message);
      },
    });
  };
  if (claims.length === 0) {
    return <EmptyState title="No evidence claims yet." />;
  }
  return (
    <div>
      {claims.map((c) => (
        <ClaimCard key={c.id} claim={c} />
      ))}
      <PaginationControls
        hasNext={hasNext}
        loading={isLoadingNext}
        error={loadError}
        onLoadNext={loadNextPage}
      />
    </div>
  );
}

export function EvidencePanel({ embedded = false }: { embedded?: boolean }) {
  return (
    <div>
      <PageHeader level={embedded ? 2 : 1} eyebrow="Research record" title="Evidence" description="Document claims, inferred suggestions and measured outcomes are distinct — contradictions stay visible, never silently resolved." actions={<Link className="cs-btn" to="/evidence/quality">Data quality &amp; revocation</Link>} />
      <Suspense fallback={<LoadingState label="loading claims…" />}>
        <Claims />
      </Suspense>
    </div>
  );
}
