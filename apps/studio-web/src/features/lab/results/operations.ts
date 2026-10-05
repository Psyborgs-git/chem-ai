import { graphql } from "react-relay";

export const TaskExecutionsQuery = graphql`
  query labResultsTaskExecutionsQuery($taskId: ID!) {
    taskExecutions(taskId: $taskId) {
      id
      planId
      status
      historical
      actual
      deviations
      observations
      batches {
        id
        label
        payload
        samples {
          id
          label
          kind
          measurements {
            id
            method
            repeatType
            metric
            valueType
            value
            conditions
            applicable
            applicabilityNote
            status
            reviewNote
            supersededBy
            amendments
          }
        }
      }
    }
  }
`;

export const ReplicationSummaryQuery = graphql`
  query labResultsReplicationSummaryQuery($executionId: ID!) {
    replicationSummary(executionId: $executionId)
  }
`;

export const ContractCheckQuery = graphql`
  query labResultsContractCheckQuery($measurementId: ID!, $metric: JSON!) {
    measurementContractCheck(measurementId: $measurementId, metric: $metric)
  }
`;

export const ExecutionOpenMutation = graphql`
  mutation labResultsExecutionOpenMutation($input: ExecutionOpenInput!) {
    lab {
      measurements {
        executionOpen(input: $input) {
          execution {
            id
            status
          }
          errors {
            code
            message
            fieldPath
          }
        }
      }
    }
  }
`;

export const ExecutionHistoricalMutation = graphql`
  mutation labResultsExecutionHistoricalMutation(
    $input: ExecutionHistoricalInput!
  ) {
    lab {
      measurements {
        executionHistoricalImport(input: $input) {
          execution {
            id
            status
            historical
          }
          errors {
            code
            message
            fieldPath
          }
        }
      }
    }
  }
`;

export const ExecutionCloseMutation = graphql`
  mutation labResultsExecutionCloseMutation($input: ExecutionCloseInput!) {
    lab {
      measurements {
        executionClose(input: $input) {
          execution {
            id
            status
          }
          errors {
            code
            message
          }
        }
      }
    }
  }
`;

export const ActualsRecordMutation = graphql`
  mutation labResultsActualsRecordMutation($input: ActualsRecordInput!) {
    lab {
      measurements {
        actualsRecord(input: $input) {
          execution {
            id
            status
          }
          errors {
            code
            message
          }
        }
      }
    }
  }
`;

export const BatchAddMutation = graphql`
  mutation labResultsBatchAddMutation($input: BatchAddInput!) {
    lab {
      measurements {
        batchAdd(input: $input) {
          batch {
            id
            label
          }
          errors {
            code
            message
          }
        }
      }
    }
  }
`;

export const SampleAddMutation = graphql`
  mutation labResultsSampleAddMutation($input: SampleAddInput!) {
    lab {
      measurements {
        sampleAdd(input: $input) {
          sample {
            id
            label
            kind
          }
          errors {
            code
            message
          }
        }
      }
    }
  }
`;

export const MeasurementRecordMutation = graphql`
  mutation labResultsMeasurementRecordMutation(
    $input: MeasurementRecordInput!
  ) {
    lab {
      measurements {
        measurementRecord(input: $input) {
          measurement {
            id
            status
            valueType
          }
          errors {
            code
            message
            fieldPath
          }
        }
      }
    }
  }
`;

export const MeasurementReviewMutation = graphql`
  mutation labResultsMeasurementReviewMutation(
    $input: MeasurementReviewInput!
  ) {
    lab {
      measurements {
        measurementReview(input: $input) {
          measurement {
            id
            status
          }
          errors {
            code
            message
          }
        }
      }
    }
  }
`;

export const MeasurementApplicabilityMutation = graphql`
  mutation labResultsMeasurementApplicabilityMutation(
    $input: MeasurementApplicabilityInput!
  ) {
    lab {
      measurements {
        measurementApplicability(input: $input) {
          measurement {
            id
            applicable
          }
          errors {
            code
            message
          }
        }
      }
    }
  }
`;

export const MeasurementAmendMutation = graphql`
  mutation labResultsMeasurementAmendMutation($input: MeasurementAmendInput!) {
    lab {
      measurements {
        measurementAmend(input: $input) {
          measurement {
            id
            status
            supersededBy
          }
          errors {
            code
            message
            fieldPath
          }
        }
      }
    }
  }
`;
