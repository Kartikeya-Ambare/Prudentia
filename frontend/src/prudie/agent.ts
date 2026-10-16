import type { PrudieState } from './engine';

/** What your agent is doing. Map each phase to a Prudie action in one place. */
export type AgentPhase =
  | 'idle'
  | 'chat-open'
  | 'typing'
  | 'sending'
  | 'thinking'
  | 'web-or-rag'
  | 'code-or-sql'
  | 'streaming'
  | 'done';

export const PHASE_TO_STATE: Record<AgentPhase, PrudieState> = {
  idle: 'idle',
  'chat-open': 'skate', // user opens the chat: rolls in on a skateboard, then waves
  typing: 'look', // user is typing: Prudie reads the chat box
  sending: 'search', // user hit send
  thinking: 'search', // model is thinking
  'web-or-rag': 'search', // web or RAG lookup
  'code-or-sql': 'code', // code or SQL tool
  streaming: 'look', // tokens streaming: eyes follow the text
  done: 'thumbsup', // answer delivered
};

export const prudieStateFor = (phase: AgentPhase): PrudieState => PHASE_TO_STATE[phase];
