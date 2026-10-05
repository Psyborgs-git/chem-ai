import { graphql } from "react-relay";

export const TaskSessionsQuery = graphql`
  query researchTaskSessionsQuery($taskId: ID!) {
    taskSessions(taskId: $taskId, first: 50) {
      edges {
        node {
          id
          status
          startContractRevisionId
          endSnapshot
          createdAt
          endedAt
          startManifest {
            id
            compilerVersion
            tokenBudget
            tokenEstimate
            overBudget
            items
            omitted
            warnings
          }
        }
      }
    }
    taskQuestions(taskId: $taskId) {
      id
      question
      blocking
      status
      resolution
    }
    taskSummaries(taskId: $taskId) {
      id
      body
      sourceIds
      coverage
      generator
      stale
      createdAt
    }
  }
`;

export const SessionStartMutation = graphql`
  mutation researchSessionStartMutation($input: SessionStartInput!) {
    research {
      sessionStart(input: $input) {
        session {
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

export const SessionEndMutation = graphql`
  mutation researchSessionEndMutation($input: SessionEndInput!) {
    research {
      sessionEnd(input: $input) {
        session {
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

export const QuestionRaiseMutation = graphql`
  mutation researchQuestionRaiseMutation($input: QuestionRaiseInput!) {
    research {
      questionRaise(input: $input) {
        question {
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
