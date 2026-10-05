import { graphql } from "react-relay";

export const ProjectListQuery = graphql`
  query tasksProjectListQuery {
    projects(first: 50) {
      edges {
        node {
          id
          slug
          name
          status
        }
      }
    }
  }
`;

export const ProjectTasksQuery = graphql`
  query tasksProjectTasksQuery($projectId: ID!) {
    projectTasks(projectId: $projectId, first: 50) {
      edges {
        node {
          id
          title
          mode
          workflowState
          unresolvedInputs
          createdAt
        }
      }
    }
  }
`;

export const TaskDetailQuery = graphql`
  query tasksTaskDetailQuery($id: ID!) {
    node(id: $id) {
      ... on Task {
        id
        title
        mode
        workflowState
        targetKind
        objective
        evaluationCycle
        unresolvedInputs
        createdAt
      }
    }
  }
`;

export const TaskCreateMutation = graphql`
  mutation tasksTaskCreateMutation($input: TaskCreateInput!) {
    taskCreate(input: $input) {
      task {
        id
        title
        mode
        workflowState
        unresolvedInputs
      }
      errors {
        code
        message
        fieldPath
      }
    }
  }
`;

export const ContractDraftMutation = graphql`
  mutation tasksContractDraftMutation($input: ContractDraftCreateInput!) {
    contractDraftCreate(input: $input) {
      contractRevision {
        id
        revision
        status
      }
      errors {
        code
        message
        fieldPath
      }
    }
  }
`;

export const ContractFreezeMutation = graphql`
  mutation tasksContractFreezeMutation($input: ContractFreezeInput!) {
    contractFreeze(input: $input) {
      contractRevision {
        id
        revision
        status
      }
      errors {
        code
        message
        fieldPath
      }
    }
  }
`;
