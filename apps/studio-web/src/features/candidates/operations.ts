import { graphql } from "react-relay";

export const TaskCandidatesQuery = graphql`
  query candidatesTaskCandidatesQuery($taskId: ID!) {
    taskCandidateRevisions(taskId: $taskId, first: 50) {
      edges {
        node {
          id
          revision
          status
          eligibility
          entityKind
          entityRevisionId
          hypothesis
          payload
          parentRevisionId
          createdAt
        }
      }
    }
  }
`;

export const CandidateCreateMutation = graphql`
  mutation candidatesCreateMutation($input: CandidateCreateInput!) {
    candidates {
      create(input: $input) {
        candidate {
          id
          revision
          status
          eligibility
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

export const CandidateSubmitMutation = graphql`
  mutation candidatesSubmitMutation($input: CandidateSubmitInput!) {
    candidates {
      submit(input: $input) {
        candidate {
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
`;

export const CandidateReviewMutation = graphql`
  mutation candidatesReviewMutation($input: CandidateReviewInput!) {
    candidates {
      review(input: $input) {
        candidate {
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
`;

export const PatchProposeMutation = graphql`
  mutation candidatesPatchProposeMutation($input: CandidatePatchProposeInput!) {
    candidates {
      patchPropose(input: $input) {
        patchId
        status
        errors {
          code
          message
        }
      }
    }
  }
`;

export const PatchReviewMutation = graphql`
  mutation candidatesPatchReviewMutation($input: CandidatePatchReviewInput!) {
    candidates {
      patchReview(input: $input) {
        patchId
        status
        errors {
          code
          message
        }
      }
    }
  }
`;
