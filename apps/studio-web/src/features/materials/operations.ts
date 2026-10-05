/**
 * Materials-registry Relay operations (CS-0203).
 *
 * Transport flows exclusively through the Relay network layer —
 * the boundary checker forbids direct fetch/axios calls outside
 * `src/relay/`. The task-workspace UI composes these in CS-0206.
 */
import { graphql } from "react-relay";

export const IdentityCreateMutation = graphql`
  mutation materialsIdentityCreateMutation($input: MaterialIdentityCreateInput!) {
    materials {
      identityCreate(input: $input) {
        identity {
          id
          kind
          name
          structureStatus
          evidenceStatus
          identifiers
        }
        errors {
          code
          message
          fieldPath
        }
        clientMutationId
      }
    }
  }
`;

export const GradeCreateMutation = graphql`
  mutation materialsGradeCreateMutation($input: MaterialGradeCreateInput!) {
    materials {
      gradeCreate(input: $input) {
        grade {
          id
          supplier
          gradeName
          activeContent
        }
        errors {
          code
          message
          fieldPath
        }
        clientMutationId
      }
    }
  }
`;

export const ReferenceProductCreateMutation = graphql`
  mutation materialsReferenceCreateMutation($input: ReferenceProductCreateInput!) {
    materials {
      referenceProductCreate(input: $input) {
        product {
          id
          name
          supplier
          category
          compositionKnowledge
        }
        errors {
          code
          message
          fieldPath
        }
        clientMutationId
      }
    }
  }
`;

export const StructureReviewMutation = graphql`
  mutation materialsStructureReviewMutation($input: MaterialStructureReviewInput!) {
    materials {
      structureReview(input: $input) {
        identity {
          id
          structureStatus
          evidenceStatus
        }
        errors {
          code
          message
          fieldPath
        }
        clientMutationId
      }
    }
  }
`;

export const MatchProposeMutation = graphql`
  mutation materialsMatchProposeMutation($input: MaterialMatchProposeInput!) {
    materials {
      matchPropose(input: $input) {
        identity {
          id
          name
        }
        errors {
          code
          message
          fieldPath
        }
        clientMutationId
      }
    }
  }
`;

export const MatchReviewMutation = graphql`
  mutation materialsMatchReviewMutation($input: MaterialMatchReviewInput!) {
    materials {
      matchReview(input: $input) {
        identity {
          id
          name
        }
        errors {
          code
          message
          fieldPath
        }
        clientMutationId
      }
    }
  }
`;

export const GradeReconcileMutation = graphql`
  mutation materialsGradeReconcileMutation($input: MaterialGradeReconcileInput!) {
    materials {
      gradeReconcile(input: $input) {
        grade {
          id
          gradeName
          reconciledInto
        }
        errors {
          code
          message
          fieldPath
        }
        clientMutationId
      }
    }
  }
`;

export const ReferenceRevisionDraftMutation = graphql`
  mutation materialsRefRevDraftMutation($input: ReferenceRevisionDraftInput!) {
    materials {
      referenceRevisionDraft(input: $input) {
        revision {
          id
          revision
          status
        }
        errors {
          code
          message
          fieldPath
        }
        clientMutationId
      }
    }
  }
`;

export const ReferenceRevisionFreezeMutation = graphql`
  mutation materialsRefRevFreezeMutation($input: ReferenceRevisionFreezeInput!) {
    materials {
      referenceRevisionFreeze(input: $input) {
        revision {
          id
          revision
          status
        }
        errors {
          code
          message
          fieldPath
        }
        clientMutationId
      }
    }
  }
`;
