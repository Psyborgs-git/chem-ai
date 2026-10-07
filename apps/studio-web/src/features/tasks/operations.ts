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

export const ProjectCreateMutation = graphql`
  mutation tasksProjectCreateMutation($input: ProjectCreateInput!) {
    projectCreate(input: $input) {
      project {
        id
        slug
        name
      }
      errors {
        code
        message
        fieldPath
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
  query tasksTaskDetailQuery($id: ID!, $includeOptimization: Boolean!, $includeAnalysis: Boolean!) {
    node(id: $id) {
      ... on Task {
        ...OptimizationPanel_task @include(if: $includeOptimization) @alias(as: "optimization")
        ...ReferenceAnalysisPanel_task @include(if: $includeAnalysis) @alias(as: "analysis")
        id
        title
        mode
        workflowState
        targetKind
        objective
        closureDecision
        evaluationCycle
        unresolvedInputs
        createdAt
        project {
          id
          name
        }
      }
    }
    # PAR-09 context header — real reads, same request as the task:
    taskContractRevisions(taskId: $id, first: 1) {
      edges {
        node {
          id
          revision
          status
          createdAt
        }
      }
    }
    taskCandidateRevisions(taskId: $id, first: 50) {
      edges {
        node {
          status
        }
      }
    }
    taskPlans(taskId: $id, first: 50) {
      edges {
        node {
          status
        }
      }
    }
    taskQuestions(taskId: $id) {
      id
      blocking
      status
    }
    taskReassessmentStatus(taskId: $id)
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

export const ContractRevisionsQuery = graphql`
  query tasksContractRevisionsQuery($taskId: ID!) {
    taskContractRevisions(taskId: $taskId, first: 50) {
      edges {
        node {
          id
          revision
          status
          contentHash
          createdAt
          payload
        }
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
        payload
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
