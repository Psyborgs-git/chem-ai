import { graphql } from "react-relay";

export const TaskReportQuery = graphql`
  query tasksReportQuery($taskId: ID!) {
    taskReport(taskId: $taskId)
  }
`;

export const TaskDecisionsQuery = graphql`
  query tasksDecisionsQuery($taskId: ID!) {
    ...DecisionsPanel_list @arguments(taskId: $taskId)
  }
`;

/** pageInfo-driven decision log (PAR-09): the immutable ledger
 * paginates like every other connection. */
export const DecisionsListFragment = graphql`
  fragment DecisionsPanel_list on Query
  @argumentDefinitions(
    taskId: { type: "ID!" }
    count: { type: "Int", defaultValue: 20 }
    cursor: { type: "String" }
  )
  @refetchable(queryName: "tasksDecisionsPaginationQuery") {
    taskDecisions(taskId: $taskId, first: $count, after: $cursor)
      @connection(key: "DecisionsPanel_list_taskDecisions") {
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
