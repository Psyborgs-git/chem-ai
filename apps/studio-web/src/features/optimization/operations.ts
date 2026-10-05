import { graphql } from "react-relay";

export const OptimizationFragment = graphql`
  fragment OptimizationPanel_task on Task {
    id
    optimizationCampaigns { id revision manifest }
  }
`;

export const CreateCampaignMutation = graphql`
  mutation optimizationCreateCampaignMutation($input: OptimizationCreateInput!) {
    optimization {
      create(input: $input) {
        task { ...OptimizationPanel_task }
        errors { code message }
      }
    }
  }
`;

export const CampaignCommandMutation = graphql`
  mutation optimizationCampaignCommandMutation($input: OptimizationCommandInput!) {
    optimization {
      command(input: $input) {
        task { ...OptimizationPanel_task }
        errors { code message }
      }
    }
  }
`;
