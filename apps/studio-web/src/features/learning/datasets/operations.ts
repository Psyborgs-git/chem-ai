import { graphql } from "react-relay";

export const DatasetSnapshotsQuery = graphql`
  query learningDatasetsQuery($taskId: ID) {
    datasetSnapshots(taskId: $taskId) {
      id
      purpose
      name
      taskId
      state
      digest
      manifest
      createdAt
      frozenAt
    }
  }
`;

export const DatasetSnapshotDriftQuery = graphql`
  query learningDatasetDriftQuery($snapshotId: ID!) {
    datasetSnapshotDrift(snapshotId: $snapshotId)
  }
`;

export const DatasetSnapshotBuildMutation = graphql`
  mutation learningDatasetBuildMutation($input: DatasetSnapshotBuildInput!) {
    learning {
      snapshotBuild(input: $input) {
        snapshot {
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

export const DatasetSnapshotFreezeMutation = graphql`
  mutation learningDatasetFreezeMutation($input: DatasetSnapshotIdInput!) {
    learning {
      snapshotFreeze(input: $input) {
        snapshot {
          id
          state
        }
        errors {
          code
          message
          safeDetails
        }
      }
    }
  }
`;

export const DatasetPrepareRunMutation = graphql`
  mutation learningDatasetPrepareMutation($input: DatasetSnapshotIdInput!) {
    learning {
      snapshotPrepareRun(input: $input) {
        report
        errors {
          code
          message
        }
      }
    }
  }
`;
