import { graphql } from "react-relay";

export const TaskCandidatesQuery = graphql`
  query candidatesTaskCandidatesQuery($taskId: ID!) {
    ...CandidatePanel_list @arguments(taskId: $taskId)
  }
`;

/** pageInfo-driven candidate list (PAR-09): the connection paginates
 * via loadNext; mutations update rows in the normalized store, and
 * creates refresh the first page with a real network refetch
 * (CS-1201 semantics preserved — never a cache replay). */
export const CandidatesListFragment = graphql`
  fragment CandidatePanel_list on Query
  @argumentDefinitions(
    taskId: { type: "ID!" }
    count: { type: "Int", defaultValue: 20 }
    cursor: { type: "String" }
  )
  @refetchable(queryName: "candidatesPaginationQuery") {
    taskCandidateRevisions(taskId: $taskId, first: $count, after: $cursor)
      @connection(key: "CandidatePanel_list_taskCandidateRevisions") {
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

/** Bounded lookup for the CandidateRevisionPicker (not a paginated
 * list — the picker needs the full accepted set in one shot). */
export const CandidateRevisionPickerQuery = graphql`
  query candidatesRevisionPickerQuery($taskId: ID!) {
    taskCandidateRevisions(taskId: $taskId, first: 50) {
      edges {
        node {
          id
          revision
          status
          entityKind
          hypothesis
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
          entityKind
          entityRevisionId
          hypothesis
          payload
          parentRevisionId
          createdAt
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
          eligibility
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
          eligibility
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
