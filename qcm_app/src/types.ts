export type UnessImage = {
  source_url: string
  local_path: string
  alt_text: string
  caption: string
  metadata?: Record<string, unknown>
}

export type UnessQuestionMetadata = {
  exam?: {
    faculty?: string
    level?: string
    year?: number
    title?: string
    dp_context?: Record<string, unknown>
  }
  provenance?: {
    source?: string
    source_url?: string
    collected_at?: string
    collection_status?: string
  }
  question?: {
    id?: string
    type_question?: string
    type_question_raw?: string
    rank?: 'A' | 'B' | ''
    rank_source?: 'ednpro' | 'official' | 'gemini' | 'admin' | 'unknown' | string
    rank_confidence?: number | null
    rank_evidence?: string[]
    support_visuel_seul?: boolean
    verification_status?: 'unverified' | 'verified' | 'unsupported' | 'pending_visual_review' | string
    dp_context?: Record<string, unknown>
    images?: UnessImage[]
  }
  propositions?: Array<{
    id: string
    statut: 'concordant' | 'desaccord' | 'incertain' | 'valide_manuellement' | string
    commentaire_desaccord?: string
  }>
}

export type CorrectionMetadata = {
  primary?: {
    source: 'ia' | 'uness' | 'validated' | string
    answer: string[]
    explanation?: string
  }
  official?: {
    source: 'UNESS' | string
    answer: string[]
    available: boolean
  }
  disagreement?: {
    present: boolean
    comments: string[]
  }
}

export type Question = {
  id: number
  prompt: string
  choices: string[]
  question_kind: 'closed' | 'open' | string
  uness?: UnessQuestionMetadata
  correction?: CorrectionMetadata
}

export type PropositionCorrection = {
  proposition_id: string
  text?: string
  selected: number | boolean
  expected: number | boolean
  rank?: string
  points: number
  discordance: string
}

export type Session = {
  id: number
  course_title?: string
  item_number?: string
  total_questions: number
  completed_at?: string | null
  score_mode?: string
  score_reason?: string
  duration_seconds?: number | null
}

export type SessionPayload = {
  session: Session
  questions: Question[]
  answers: Record<string, string>
}

export type CorrectionRow = {
  position: number
  status: 'correct' | 'incorrect' | 'unanswered' | 'not_noted' | null
  response: string
  correct_answer: string
  explanation: string
  choices: string[]
  question: Question
  correction?: CorrectionMetadata
  propositions?: PropositionCorrection[]
}

export type CorrectionPayload = {
  session: Session & {
    score_percent?: number | null
    correct_count?: number
    incorrect_count?: number
    unanswered_count?: number
  }
  rows: CorrectionRow[]
  follow_up?: FollowUp | null
}

export type FollowUp = {
  eligible: boolean
  failure_streak: number
  question_id: number
  question_prompt: string
  context: string
}
