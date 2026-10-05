import { graphql } from "react-relay";

export const TaskReportQuery = graphql`
  query tasksReportQuery($taskId: ID!) {
    taskReport(taskId: $taskId)
  }
`;

export const TaskDecisionsQuery = graphql`
  query tasksDecisionsQuery($taskId: ID!) {
    taskDecisions(taskId: $taskId, first: 50) {
      edges {
        node {
          id
          kind
          payload
          createdAt
          decidedBy {
            displayName
            kind
          }
        }
      }
    }
  }
`;
