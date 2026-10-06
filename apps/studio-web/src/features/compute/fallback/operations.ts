import { graphql } from "react-relay";

export const FallbackViewQuery = graphql`
  query fallbackRunViewQuery($runId: ID!) {
    runFallback(runId: $runId)
  }
`;

export const FallbackRequestMutation = graphql`
  mutation fallbackRequestMutation($input: RunFallbackInput!) {
    runs {
      requestFallback(input: $input) {
        run {
          id
          status
        }
        decision
        cloudAuthorized
        report
        proposal
        cloud
        errors {
          code
          message
          fieldPath
        }
      }
    }
  }
`;
