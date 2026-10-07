/** Evidence-claim Relay operations (CS-0302). */
import { graphql } from "react-relay";

export const EvidenceClaimsQuery = graphql`
  query evidenceClaimsQuery($kind: String, $status: String) {
    ...EvidencePanel_claims @arguments(kind: $kind, status: $status)
  }
`;

/** pageInfo-driven claims list (PAR-09): kind/status filters stay
 * connection-keyed so each filtered view paginates its own cursor. */
export const ClaimsFragment = graphql`
  fragment EvidencePanel_claims on Query
  @argumentDefinitions(
    kind: { type: "String" }
    status: { type: "String" }
    count: { type: "Int", defaultValue: 20 }
    cursor: { type: "String" }
  )
  @refetchable(queryName: "evidenceClaimsPaginationQuery") {
    evidenceClaims(kind: $kind, status: $status, first: $count, after: $cursor)
      @connection(key: "EvidencePanel_claims_evidenceClaims") {
      edges {
        node {
          id
          kind
          status
          subject
          statement
          locator
          originalText
          conditions
          sourceRecordId
          reviewedAt
          createdAt
        }
      }
    }
  }
`;

export const ClaimLinksQuery = graphql`
  query evidenceClaimLinksQuery($claimId: ID!) {
    claimLinks(claimId: $claimId) {
      fromClaimId
      toClaimId
      relation
      note
    }
  }
`;

export const ClaimReviewMutation = graphql`
  mutation evidenceClaimReviewMutation($input: ClaimReviewInput!) {
    evidence {
      claimReview(input: $input) {
        claim {
          id
          status
          reviewedAt
        }
        errors {
          code
          message
        }
        clientMutationId
      }
    }
  }
`;

export const ClaimLinkMutation = graphql`
  mutation evidenceClaimLinkMutation($input: ClaimLinkInput!) {
    evidence {
      claimLink(input: $input) {
        link {
          fromClaimId
          toClaimId
          relation
        }
        errors {
          code
          message
        }
        clientMutationId
      }
    }
  }
`;
