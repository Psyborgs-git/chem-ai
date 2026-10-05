import { graphql } from "react-relay";

export const TaskPlansQuery = graphql`
  query labPlansTaskPlansQuery($taskId: ID!) {
    taskPlans(taskId: $taskId, first: 50) {
      edges {
        node {
          id
          title
          status
          contentDigest
          blockers
          payload
          approvalId
          packet
          createdAt
        }
      }
    }
  }
`;

export const PlanCreateMutation = graphql`
  mutation labPlansPlanCreateMutation($input: PlanCreateInput!) {
    lab {
      planCreate(input: $input) {
        plan {
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
`;

export const PlanSubmitMutation = graphql`
  mutation labPlansPlanSubmitMutation($input: PlanIdInput!) {
    lab {
      planSubmit(input: $input) {
        plan {
          id
          status
          blockers
        }
        errors {
          code
          message
        }
      }
    }
  }
`;

export const PlanReviewMutation = graphql`
  mutation labPlansPlanReviewMutation($input: PlanReviewInput!) {
    lab {
      planReview(input: $input) {
        plan {
          id
          status
          approvalId
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

export const PacketExportMutation = graphql`
  mutation labPlansPacketExportMutation($input: PlanIdInput!) {
    lab {
      packetExport(input: $input) {
        packet
        errors {
          code
          message
        }
      }
    }
  }
`;
