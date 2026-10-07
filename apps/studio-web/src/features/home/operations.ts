import { graphql } from "react-relay";

/** Workspace landing (PAR-09): recent tasks + pending decisions —
 * tasks awaiting review are the decisions a human still has to make.
 * Both lanes come from the same keyset connection; there is no
 * second server-state cache. */
export const WorkspaceHomeQuery = graphql`
  query homeWorkspaceQuery {
    recent: tasks(first: 8) {
      edges {
        node {
          id
          title
          mode
          workflowState
          createdAt
          project {
            id
            name
          }
        }
      }
    }
    pendingDecisions: tasks(workflowState: "awaiting_review", first: 20) {
      edges {
        node {
          id
          title
          createdAt
          project {
            id
            name
          }
        }
      }
    }
  }
`;
