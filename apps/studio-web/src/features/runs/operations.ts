import { graphql } from "react-relay";

export const TaskRunsQuery = graphql`
  query runsTaskRunsQuery($taskId: ID!) {
    taskRuns(taskId: $taskId, first: 50) {
      edges {
        node {
          id
          kind
          status
          taskId
          inputSummary
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

export const CalculationCapabilityQuery = graphql`
  query runsCalculationCapabilityQuery {
    engineCapabilities {
      rdkit { status detail }
    }
  }
`;

export const DescribeStructureMutation = graphql`
  mutation runsDescribeStructureMutation($input: DescribeStructureInput!) {
    runs {
      describeStructure(input: $input) {
        run {
          id
          taskId
          kind
          status
          attemptCount
          maxAttempts
          queuedAt
          startedAt
          finishedAt
          error
          inputSummary
          resultSummary
        }
        errors { code message fieldPath }
      }
    }
  }
`;

export const RunDetailQuery = graphql`
  query runsDetailQuery($runId: ID!) {
    node(id: $runId) {
      __typename
      ... on Run {
        id
        taskId
        kind
        status
        attemptCount
        maxAttempts
        queuedAt
        startedAt
        finishedAt
        cancelRequestedAt
        deadlineAt
        error
        inputSummary
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
