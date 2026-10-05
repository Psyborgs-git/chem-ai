/** Evidence-claim Relay operations (CS-0302). */
import { graphql } from "react-relay";

export const EvidenceClaimsQuery = graphql`
  query evidenceClaimsQuery($kind: String, $status: String) {
    evidenceClaims(kind: $kind, status: $status, first: 50) {
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
