export type Question = {
  id: number
  prompt: string
  choices: string[]
  question_kind: 'closed' | 'open' | string
}

export type Session = {
  id: number
  course_title?: string
  item_number?: string
  total_questions: number
  completed_at?: string | null
}

export type SessionPayload = {
  session: Session
  questions: Question[]
  answers: Record<string, string>
}

export type CorrectionRow = {
  position: number
  status: 'correct' | 'incorrect' | 'unanswered' | null
  response: string
  correct_answer: string
  explanation: string
  choices: string[]
  question: Question
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
