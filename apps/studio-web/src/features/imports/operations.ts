/**
 * Extraction-review Relay operations (CS-0302). Transport flows
 * exclusively through the Relay network layer.
 */
import { graphql } from "react-relay";

export const ImportBatchesQuery = graphql`
  query importsBatchesQuery {
    importBatches(first: 50) {
      edges {
        node {
          id
          originalName
          detectedType
          parserName
          parserVersion
          sourceRevision
          status
          recordCount
          findings
          createdAt
        }
      }
    }
  }
`;

export const ImportRecordsQuery = graphql`
  query importsRecordsQuery($batchId: ID!) {
    importRecords(batchId: $batchId, first: 50) {
      edges {
        node {
          id
          kind
          locator
          originalText
          payload
          flags
          confidence
          status
        }
      }
    }
  }
`;

export const ArtifactImportMutation = graphql`
  mutation importsArtifactImportMutation($input: ImportArtifactInput!) {
    imports {
      artifactImport(input: $input) {
        batch {
          id
          status
          recordCount
          findings
        }
        deduplicated
        errors {
          code
          message
        }
        clientMutationId
      }
    }
  }
`;

export const RecordReviewMutation = graphql`
  mutation importsRecordReviewMutation($input: ReviewRecordInput!) {
    imports {
      recordReview(input: $input) {
        record {
          id
          status
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

export const RecordPromoteMutation = graphql`
  mutation importsRecordPromoteMutation($input: PromoteRecordInput!) {
    imports {
      recordPromote(input: $input) {
        claim {
          id
          status
          kind
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
