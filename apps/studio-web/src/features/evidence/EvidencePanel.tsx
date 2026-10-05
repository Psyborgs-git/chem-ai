/** Evidence panel (CS-0302, §10): claims grouped by kind — document
 * claims, inferred suggestions and measured outcomes stay visibly
 * distinct. Contradiction links keep both sides on screen. */
import { Suspense, useState } from "react";
import { Link } from "react-router";
import { useLazyLoadQuery, useMutation } from "react-relay";

import {
  Badge,
  Button,
  EmptyState,
  EvidenceTypeLabel,
  LoadingState,
  SourceCitation,
} from "../../components";
import type { evidenceClaimsQuery } from "../../__generated__/evidenceClaimsQuery.graphql";
import type { evidenceClaimLinksQuery } from "../../__generated__/evidenceClaimLinksQuery.graphql";
import type { evidenceClaimReviewMutation } from "../../__generated__/evidenceClaimReviewMutation.graphql";
import {
  ClaimLinksQuery,
  ClaimReviewMutation,
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

type ClaimNode =
  evidenceClaimsQuery["response"]["evidenceClaims"]["edges"][number]["node"];

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
  const subject = JSON.stringify(claim.subject);
  const statement = JSON.stringify(claim.statement);
  return (
    <article data-claim-id={claim.id} data-status={claim.status}>
      <header>
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
      <p>
        <code>{subject}</code> → <code>{statement}</code>
      </p>
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
        <p>
          conditions: <code>{JSON.stringify(claim.conditions)}</code>
        </p>
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
    </article>
  );
}

function Claims() {
  const data = useLazyLoadQuery<evidenceClaimsQuery>(EvidenceClaimsQuery, {});
  const claims = data.evidenceClaims.edges.map((e) => e.node);
  if (claims.length === 0) {
    return <EmptyState title="No evidence claims yet." />;
  }
  return (
    <div>
      {claims.map((c) => (
        <ClaimCard key={c.id} claim={c} />
      ))}
    </div>
  );
}

export function EvidencePanel() {
  return (
    <div>
      <h1>Evidence</h1>
      <p>
        Document claims, inferred suggestions and measured outcomes are
        distinct — contradictions stay visible, never silently resolved.
      </p>
      <p>
        <Link to="/evidence/quality">Data quality &amp; revocation</Link>
      </p>
      <Suspense fallback={<LoadingState label="loading claims…" />}>
        <Claims />
      </Suspense>
    </div>
  );
}
