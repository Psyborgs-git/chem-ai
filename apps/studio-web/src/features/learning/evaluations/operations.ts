import { graphql } from "react-relay";

export const EvaluationSuitesQuery = graphql`
  query learningEvaluationSuitesQuery($taskId: ID) {
    evaluationSuites(taskId: $taskId) {
      id
      taskId
      name
      version
      purpose
      kind
      state
      definition
      digest
      capability
      createdAt
      updatedAt
    }
  }
`;

export const EvaluationReleasesQuery = graphql`
  query learningEvaluationReleasesQuery($taskId: ID) {
    modelReleases(taskId: $taskId) {
      id
      name
      state
    }
  }
`;

export const EvaluationRunsQuery = graphql`
  query learningEvaluationRunsQuery($modelReleaseId: ID, $evaluationSuiteId: ID) {
    evaluationRuns(
      modelReleaseId: $modelReleaseId
      evaluationSuiteId: $evaluationSuiteId
    ) {
      id
      suiteId
      suiteDigest
      modelReleaseId
      baselineReleaseId
      state
      backend
      comparison
      contamination
      blockers
      capability
      error
      createdAt
    }
  }
`;

export const PromotionDecisionQuery = graphql`
  query learningPromotionDecisionQuery($modelReleaseId: ID!) {
    promotionDecision(modelReleaseId: $modelReleaseId) {
      id
      modelReleaseId
      evaluationRunId
      eligible
      blockers
      modelCard
      decisionDigest
      approvalId
      createdAt
    }
  }
`;

export const EvaluationSuiteCreateMutation = graphql`
  mutation learningEvaluationSuiteCreateMutation(
    $input: EvaluationSuiteCreateInput!
  ) {
    learning {
      evaluationSuiteCreate(input: $input) {
        evaluationSuite {
          id
          state
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const EvaluationSuiteLabelsMutation = graphql`
  mutation learningEvaluationSuiteLabelsMutation(
    $input: EvaluationSuiteLabelsInput!
  ) {
    learning {
      evaluationSuiteLabels(input: $input) {
        evaluationSuite {
          id
          state
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const EvaluationSuiteFreezeMutation = graphql`
  mutation learningEvaluationSuiteFreezeMutation(
    $input: EvaluationSuiteIdInput!
  ) {
    learning {
      evaluationSuiteFreeze(input: $input) {
        evaluationSuite {
          id
          state
          digest
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const EvaluationRunStartMutation = graphql`
  mutation learningEvaluationRunStartMutation($input: EvaluationRunStartInput!) {
    learning {
      evaluationRunStart(input: $input) {
        evaluationRun {
          id
          state
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const PromotionDecideMutation = graphql`
  mutation learningPromotionDecideMutation($input: PromotionDecideInput!) {
    learning {
      promotionDecide(input: $input) {
        promotionDecision {
          id
          eligible
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const PromotionApproveMutation = graphql`
  mutation learningPromotionApproveMutation($input: PromotionApproveInput!) {
    learning {
      promotionApprove(input: $input) {
        promotionDecision {
          id
          approvalId
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const PromotionPromoteMutation = graphql`
  mutation learningPromotionPromoteMutation($input: PromotionPromoteInput!) {
    learning {
      promotionPromote(input: $input) {
        promotionDecision {
          id
          eligible
        }
        errors {
          code
          message
        }
      }
    }
  }
`;
