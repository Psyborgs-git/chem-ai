import { graphql } from "react-relay";

export const TaskRunsQuery = graphql`
  query runsTaskRunsQuery($taskId: ID!) {
    taskRuns(taskId: $taskId, first: 50) {
      edges {
        node {
          id
          kind
          status
          attemptCount
          maxAttempts
          queuedAt
          startedAt
          finishedAt
          cancelRequestedAt
          error
          resultSummary
          attempts {
            id
            status
            queue
            workerId
            attemptNumber
            startedAt
            finishedAt
            error
          }
        }
      }
    }
  }
`;

export const RunRequestMutation = graphql`
  mutation runsRequestMutation($input: RunRequestInput!) {
    runs {
      request(input: $input) {
        run {
          id
          status
        }
        errors {
          code
          message
          fieldPath
        }
      }
    }
  }
`;

export const RunRequestCancelMutation = graphql`
  mutation runsRequestCancelMutation($input: RunCancelInput!) {
    runs {
      requestCancel(input: $input) {
        run {
          id
          status
          cancelRequestedAt
        }
        errors {
          code
          message
          fieldPath
        }
      }
    }
  }
`;
