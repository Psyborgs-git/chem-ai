import { graphql } from "react-relay";

export const ModelReleasesQuery = graphql`
  query learningModelReleasesQuery($taskId: ID) {
    modelReleases(taskId: $taskId) {
      id
      taskId
      name
      state
      snapshotId
      trainingRunId
      baseModelId
      architecture
      baseSha256
      licenseId
      tokenizerKind
      tokenizerSha256
      adapterSha256
      adapterMethod
      servingFormat
      conversions
      validation
      capability
      provenance
      approvalId
      createdAt
      updatedAt
    }
  }
`;

export const ServingPointerQuery = graphql`
  query learningServingPointerQuery {
    servingPointer {
      releaseId
      revision
      reason
      updatedAt
    }
  }
`;

export const SessionModelPinsQuery = graphql`
  query learningSessionModelPinsQuery($taskId: ID) {
    sessionModelPins(taskId: $taskId) {
      sessionId
      releaseId
      createdAt
    }
  }
`;

export const ModelTrainingRunsQuery = graphql`
  query learningModelTrainingRunsQuery($taskId: ID) {
    trainingRuns(taskId: $taskId) {
      id
      name
      state
    }
  }
`;

export const ModelReleaseRegisterMutation = graphql`
  mutation learningModelReleaseRegisterMutation($input: ModelReleaseRegisterInput!) {
    learning {
      modelReleaseRegister(input: $input) {
        modelRelease {
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

export const ModelReleaseValidateMutation = graphql`
  mutation learningModelReleaseValidateMutation($input: ModelReleaseIdInput!) {
    learning {
      modelReleaseValidate(input: $input) {
        modelRelease {
          id
          state
          validation
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const ModelReleaseConvertMutation = graphql`
  mutation learningModelReleaseConvertMutation($input: ModelReleaseConvertInput!) {
    learning {
      modelReleaseConvert(input: $input) {
        modelRelease {
          id
          state
          conversions
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const ModelReleaseApproveMutation = graphql`
  mutation learningModelReleaseApproveMutation($input: ModelReleaseApproveInput!) {
    learning {
      modelReleaseApprove(input: $input) {
        modelRelease {
          id
          state
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

export const ModelReleasePromoteMutation = graphql`
  mutation learningModelReleasePromoteMutation($input: ModelReleaseIdInput!) {
    learning {
      modelReleasePromote(input: $input) {
        modelRelease {
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

export const ModelReleaseRollbackMutation = graphql`
  mutation learningModelReleaseRollbackMutation($input: ModelReleaseRollbackInput!) {
    learning {
      modelReleaseRollback(input: $input) {
        modelRelease {
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

export const SessionModelBindMutation = graphql`
  mutation learningSessionModelBindMutation($input: SessionModelBindInput!) {
    learning {
      sessionModelBind(input: $input) {
        modelRelease {
          id
          state
          name
        }
        validation
        errors {
          code
          message
          safeDetails
        }
      }
    }
  }
`;
