import { graphql } from "react-relay";

export const ProvidersQuery = graphql`
  query providersSettingsQuery {
    canManageInferenceProviders
    inferenceCredentialCleanupPending
    inferenceProviders {
      id revision name kind baseUrl model apiStyle enabled supportsTools hasApiKey
      lastTestStatus lastTestAt createdAt updatedAt
    }
  }
`;

export const ProviderSaveMutation = graphql`
  mutation providersSaveMutation($input: InferenceProviderSaveInput!) {
    providers {
      save(input: $input) {
        provider { id revision name kind baseUrl model apiStyle enabled supportsTools hasApiKey lastTestStatus lastTestAt createdAt updatedAt }
        errors { code fieldPath }
      }
    }
  }
`;

export const ProviderDeleteMutation = graphql`
  mutation providersDeleteMutation($input: InferenceProviderDeleteInput!) {
    providers {
      delete(input: $input) {
        deleted credentialCleanupPending
        errors { code fieldPath }
      }
    }
  }
`;

export const ProviderTestMutation = graphql`
  mutation providersTestMutation($input: InferenceProviderTestInput!) {
    providers {
      test(input: $input) {
        provider { id revision lastTestStatus lastTestAt }
        status
        errors { code fieldPath }
      }
    }
  }
`;

export const ProviderCleanupMutation = graphql`
  mutation providersCleanupMutation {
    providers { cleanupCredentials { pending errors { code fieldPath } } }
  }
`;
