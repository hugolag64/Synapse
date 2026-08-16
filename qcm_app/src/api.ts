import type { CorrectionPayload, SessionPayload } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) throw new Error((await response.json()).detail || 'Erreur QCM')
  return response.json() as Promise<T>
}

export const fetchSession = (id: number) => request<SessionPayload>(`/api/qcm/sessions/${id}`)

/** Relit la correction d'une session déjà répondue, sans la finaliser. */
export const fetchCorrection = (id: number) =>
  request<CorrectionPayload>(`/api/qcm/sessions/${id}/correction`)

export const saveAttempt = (sessionId: number, questionId: number, response: string, durationSeconds?: number) =>
  request(`/api/qcm/sessions/${sessionId}/attempts`, {
    method: 'POST',
    body: JSON.stringify({ question_id: questionId, response, duration_seconds: durationSeconds }),
  })

export const completeSession = (id: number, timedOut = false) =>
  request<CorrectionPayload>(`/api/qcm/sessions/${id}/complete`, {
    method: 'POST',
    body: timedOut ? JSON.stringify({ timed_out: true }) : undefined,
  })

export const replaySession = async (id: number) =>
  (await request<{ session_id: number }>(`/api/qcm/sessions/${id}/replay`, { method: 'POST' })).session_id

export const followUpAction = (sessionId: number, action: 'lacune' | 'anchor' | 'ignore', questionId?: number) =>
  request<{ ok: boolean; message: string }>(`/api/qcm/sessions/${sessionId}/follow-up`, {
    method: 'POST',
    body: JSON.stringify({ action, question_id: questionId }),
  })
