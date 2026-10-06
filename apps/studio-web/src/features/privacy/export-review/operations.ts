import { graphql } from "react-relay";

export const ExportReviewQuery = graphql`
  query exportReviewQuery($proposalId: ID!) {
    exportReview(proposalId: $proposalId)
  }
`;

export const ExportPrepareMutation = graphql`
  mutation exportPrepareMutation($input: ExportPrepareInput!) {
    exports {
      prepare(input: $input) {
        view
        errors {
          code
          message
          fieldPath
        }
      }
    }
  }
`;

export const ExportDecideMutation = graphql`
  mutation exportDecideMutation($input: ExportDecideInput!) {
    exports {
      decide(input: $input) {
        view
        errors {
          code
          message
          fieldPath
        }
      }
    }
  }
`;

export const ExportSetClassificationMutation = graphql`
  mutation exportSetClassificationMutation($input: ExportSetClassificationInput!) {
    exports {
      setClassification(input: $input) {
        view
        errors {
          code
          message
          fieldPath
        }
      }
    }
  }
`;
