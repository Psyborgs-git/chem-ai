import { graphql } from "react-relay";

export const TrainingRunsQuery = graphql`
  query learningTrainingRunsQuery($taskId: ID) {
    trainingRuns(taskId: $taskId) {
      id
      taskId
      name
      state
      snapshotId
      snapshotDigest
      specDigest
      datasetDigest
      datasetManifest
      telemetry
      checkpoints
      resumeFrom
      provenance
      capability
      error
      runId
      attemptId
      approvalId
      createdAt
      updatedAt
    }
  }
`;

export const TrainingSnapshotsQuery = graphql`
  query learningTrainingSnapshotsQuery($taskId: ID) {
    datasetSnapshots(taskId: $taskId) {
      id
      purpose
      name
      state
      digest
    }
  }
`;

export const TrainingRunCreateMutation = graphql`
  mutation learningTrainingRunCreateMutation($input: TrainingRunCreateInput!) {
    learning {
      trainingRunCreate(input: $input) {
        trainingRun {
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

export const TrainingRunSubmitMutation = graphql`
  mutation learningTrainingRunSubmitMutation($input: TrainingRunIdInput!) {
    learning {
      trainingRunSubmit(input: $input) {
        trainingRun {
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

export const TrainingRunApproveMutation = graphql`
  mutation learningTrainingRunApproveMutation($input: TrainingRunApproveInput!) {
    learning {
      trainingRunApprove(input: $input) {
        trainingRun {
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

export const TrainingRunQueueMutation = graphql`
  mutation learningTrainingRunQueueMutation($input: TrainingRunIdInput!) {
    learning {
      trainingRunQueue(input: $input) {
        trainingRun {
          id
          state
          attemptId
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const TrainingRunExecuteMutation = graphql`
  mutation learningTrainingRunExecuteMutation($input: TrainingRunExecuteInput!) {
    learning {
      trainingRunExecute(input: $input) {
        trainingRun {
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

export const TrainingRunCancelMutation = graphql`
  mutation learningTrainingRunCancelMutation($input: TrainingRunIdInput!) {
    learning {
      trainingRunCancel(input: $input) {
        trainingRun {
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

export const TrainingRunResumeMutation = graphql`
  mutation learningTrainingRunResumeMutation($input: TrainingRunIdInput!) {
    learning {
      trainingRunResume(input: $input) {
        trainingRun {
          id
          state
          attemptId
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const TrainingRunTransitionMutation = graphql`
  mutation learningTrainingRunTransitionMutation(
    $input: TrainingRunTransitionInput!
  ) {
    learning {
      trainingRunTransition(input: $input) {
        trainingRun {
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
