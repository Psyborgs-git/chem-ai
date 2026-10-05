import { graphql } from "react-relay";

export const ReferenceAnalysisFragment = graphql`
  fragment ReferenceAnalysisPanel_task on Task {
    id
    analyticalSeries { id label method interpretationState manifest }
    analyticalComparisons { id manifest }
  }
`;

export const AnalyticalIngestMutation = graphql`
  mutation referenceAnalysisIngestMutation($input: AnalyticalIngestInput!) {
    analytical {
      ingest(input: $input) {
        task { ...ReferenceAnalysisPanel_task }
        errors { code message }
      }
    }
  }
`;

export const AnalyticalCompareMutation = graphql`
  mutation referenceAnalysisCompareMutation($input: AnalyticalCompareInput!) {
    analytical {
      compare(input: $input) {
        task { ...ReferenceAnalysisPanel_task }
        errors { code message }
      }
    }
  }
`;
