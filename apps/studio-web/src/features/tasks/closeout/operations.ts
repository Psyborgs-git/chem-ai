import { graphql } from "react-relay";

export const TaskEvaluationQuery = graphql`
  query tasksCloseoutEvaluationQuery($taskId: ID!) {
    taskEvaluation(taskId: $taskId)
    taskReassessmentStatus(taskId: $taskId)
  }
`;

export const TaskTransitionMutation = graphql`
  mutation tasksCloseoutTransitionMutation($input: TaskTransitionInput!) {
    taskTransition(input: $input) {
      task {
        id
        workflowState
      }
      errors {
        code
        message
        fieldPath
      }
    }
  }
`;

export const TaskCloseMutation = graphql`
  mutation tasksCloseoutCloseMutation($input: TaskCloseInput!) {
    taskClose(input: $input) {
      task {
        id
        workflowState
        closureDecision
      }
      errors {
        code
        message
        fieldPath
      }
    }
  }
`;
