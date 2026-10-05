import { graphql } from "react-relay";

export const QualityReportQuery = graphql`
  query qualityQualityReportQuery($batchId: ID) {
    dataQualityReport(batchId: $batchId)
  }
`;

export const SourceRevokeMutation = graphql`
  mutation qualitySourceRevokeMutation($input: SourceRevokeInput!) {
    imports {
      sourceRevoke(input: $input) {
        revocationId
        report
        errors {
          code
          message
          fieldPath
        }
      }
    }
  }
`;

export const RevocationImpactQuery = graphql`
  query qualityRevocationImpactQuery($artifactId: String!) {
    revocationImpact(artifactId: $artifactId)
  }
`;
