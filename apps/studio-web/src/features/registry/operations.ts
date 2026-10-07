/**
 * Registry Relay operations (PAR-07): searchable feeds over the
 * materials + formulation registry and the formulations.* mutation
 * group. Pickers resolve human-typed names to canonical IDs — raw
 * uuid entry is never the normal path (CS-1201).
 */
import { graphql } from "react-relay";

export const RegistryIdentitiesQuery = graphql`
  query registryIdentitiesQuery($search: String, $first: Int, $after: String) {
    materialIdentities(search: $search, first: $first, after: $after) {
      edges {
        node {
          id
          kind
          name
          structureStatus
          evidenceStatus
          identifiers
          aliases
          createdAt
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;

export const RegistryGradesQuery = graphql`
  query registryGradesQuery($materialId: ID, $search: String, $first: Int) {
    materialGrades(materialId: $materialId, search: $search, first: $first) {
      edges {
        node {
          id
          supplier
          gradeName
          activeContent
          specifications
          reconciledInto
          createdAt
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;

export const RegistryProductsQuery = graphql`
  query registryProductsQuery($search: String, $first: Int) {
    referenceProducts(search: $search, first: $first) {
      edges {
        node {
          id
          name
          supplier
          category
          compositionKnowledge
          aliases
          createdAt
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;

export const RegistryProductRevisionsQuery = graphql`
  query registryProductRevisionsQuery($productId: ID!, $first: Int) {
    referenceProductRevisions(productId: $productId, first: $first) {
      edges {
        node {
          id
          revision
          status
          payload
          contentHash
          createdAt
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;

export const RegistryFamiliesQuery = graphql`
  query registryFamiliesQuery($search: String, $first: Int) {
    formulationFamilies(search: $search, first: $first) {
      edges {
        node {
          id
          name
          description
          createdAt
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;

export const RegistryFormulationRevisionsQuery = graphql`
  query registryFormulationRevisionsQuery(
    $familyId: ID
    $search: String
    $first: Int
  ) {
    formulationRevisions(familyId: $familyId, search: $search, first: $first) {
      edges {
        node {
          id
          revision
          status
          payload
          parentRevisionId
          familyName
          createdAt
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;

export const RegistryProcessRevisionsQuery = graphql`
  query registryProcessRevisionsQuery($familyId: ID!, $first: Int) {
    processRevisions(familyId: $familyId, first: $first) {
      edges {
        node {
          id
          revision
          status
          payload
          createdAt
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;

/** Node fetch for diff review — a stored uuid becomes a GlobalID and
 * resolves through the same scoped node() path (§8.2). */
export const RegistryRevisionNodesQuery = graphql`
  query registryRevisionNodesQuery($ids: [ID!]!) {
    nodes(ids: $ids) {
      id
      ... on FormulationRevision {
        revision
        status
        payload
        parentRevisionId
        familyName
      }
      ... on ProcessRevision {
        revision
        status
        payload
      }
    }
  }
`;

export const RegistryFamilyCreateMutation = graphql`
  mutation registryFamilyCreateMutation($input: FormulationFamilyCreateInput!) {
    formulations {
      familyCreate(input: $input) {
        family {
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

export const RegistryRevisionDraftMutation = graphql`
  mutation registryRevisionDraftMutation($input: FormulationRevisionDraftInput!) {
    formulations {
      revisionDraft(input: $input) {
        revision {
          id
          revision
          status
          payload
          parentRevisionId
          familyName
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

export const RegistryRevisionAcceptMutation = graphql`
  mutation registryRevisionAcceptMutation($input: FormulationRevisionIdInput!) {
    formulations {
      revisionAccept(input: $input) {
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

export const RegistryProcessDraftMutation = graphql`
  mutation registryProcessDraftMutation($input: ProcessRevisionDraftInput!) {
    formulations {
      processDraft(input: $input) {
        revision {
          id
          revision
          status
          payload
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

export const RegistryProcessAcceptMutation = graphql`
  mutation registryProcessAcceptMutation($input: ProcessRevisionIdInput!) {
    formulations {
      processAccept(input: $input) {
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
