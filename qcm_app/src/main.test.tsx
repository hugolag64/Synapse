import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeAll, describe, expect, it } from 'vitest'
import type { CorrectionRow, SessionPayload } from './types'

let components: typeof import('./main')

beforeAll(async () => {
  document.body.innerHTML = '<div id="root"></div>'
  components = await import('./main')
})

const unessQuestion = {
  exam: {
    faculty: 'Université Paris Cité',
    level: 'DFASM3',
    year: 2026,
    dp_context: { text: 'Une personne âgée présente une confusion aiguë.' },
  },
  provenance: {
    source_url: 'https://entrainement.uness.example/review/42',
    collected_at: '2026-07-30T09:15:00+02:00',
    collection_status: 'complete',
  },
  question: {
    verification_status: 'verified',
    dp_context: { text: 'Les symptômes fluctuent au cours de la journée.' },
    images: [
      {
        source_url: 'images/horloge.png',
        local_path: 'imports/media/horloge.png',
        alt_text: 'Test de l’horloge',
        caption: 'Dessin du patient',
      },
    ],
    support_visuel_seul: true,
  },
  propositions: [
    {
      id: 'A',
      statut: 'desaccord',
      commentaire_desaccord: 'Le cours local contredit la correction officielle.',
    },
  ],
}

describe('UNESS replay disclosure', () => {
  it('keeps internal EDNpro dossier identifiers out of the visible context', () => {
    expect((components as any).contextText({
      dossier_id: 'dossier-1',
      dossier_number: 1,
      dossier_type: 'KFP',
      dossier_context: 'Patient stable.',
    })).toBe('Patient stable.')
  })

  it('renders the unified EDN mode and proposition-level correction', () => {
    const Correction = (components as any).Correction
    expect(typeof Correction).toBe('function')
    const payload = {
      session: {
        id: 12,
        total_questions: 1,
        course_title: 'Cardiologie',
        score_percent: 50,
        score_mode: 'edn',
        correct_count: 0,
        incorrect_count: 1,
      },
      rows: [{
        position: 1,
        status: 'incorrect',
        response: 'A',
        correct_answer: 'B',
        explanation: 'Correction EDN.',
        choices: ['A', 'B'],
        question: {
          id: 1,
          prompt: 'Question',
          choices: ['A', 'B'],
          question_kind: 'closed',
        },
        propositions: [
          { proposition_id: 'A', text: 'A', selected: 1, expected: 0, rank: 'A', points: 0, discordance: 'exces' },
          { proposition_id: 'B', text: 'B', selected: 0, expected: 1, rank: '', points: 0, discordance: 'omission' },
        ],
      }],
      follow_up: null,
    }

    const markup = renderToStaticMarkup(
      createElement(Correction as any, { payload, onReplay: () => undefined }),
    )

    expect(markup).toContain('Barème EDN propositionnel')
    expect(markup).toContain('A')
    expect(markup).toContain('omission')
    expect(markup).toContain('Rang A')
    expect(markup).not.toContain('Validé Rang A')
  })

  it('renders DP context, the imported image, and the visual-only warning in the reader', () => {
    const payload: SessionPayload = {
      session: { id: 12, total_questions: 1, course_title: 'Gériatrie' },
      questions: [
        {
          id: 7,
          prompt: 'Concernant le delirium :',
          choices: ['Réponse IA', 'Réponse officielle'],
          question_kind: 'closed',
          uness: unessQuestion,
        },
      ],
      answers: {},
    }

    const markup = renderToStaticMarkup(
      createElement(components.Reader, { payload, onCorrection: () => undefined }),
    )

    expect(markup).toContain('Une personne âgée présente une confusion aiguë.')
    expect(markup).toContain('Les symptômes fluctuent au cours de la journée.')
    expect(markup).toContain('Test de l’horloge')
    expect(markup).toContain('/api/qcm/sessions/12/questions/7/images/0')
    expect(markup).toContain('Support visuel uniquement')
    expect(markup).not.toContain('dossier-1')
    expect(markup).not.toContain('KFP')
  })

  it('shows a visible divergence warning and secondary official correction', () => {
    const row: CorrectionRow = {
      position: 1,
      status: 'incorrect',
      response: 'Réponse officielle',
      correct_answer: '["Réponse IA"]',
      explanation: 'Explication IA indépendante.',
      choices: ['Réponse IA', 'Réponse officielle'],
      question: {
        id: 7,
        prompt: 'Concernant le delirium :',
        choices: ['Réponse IA', 'Réponse officielle'],
        question_kind: 'closed',
        uness: unessQuestion,
      },
      correction: {
        primary: {
          source: 'ia',
          answer: ['Réponse IA'],
          explanation: 'Explication IA indépendante.',
        },
        official: {
          source: 'UNESS',
          answer: ['Réponse officielle'],
          available: true,
        },
        disagreement: {
          present: true,
          comments: ['Le cours local contredit la correction officielle.'],
        },
      },
    }

    const markup = renderToStaticMarkup(
      createElement(components.CorrectionCard, { row, sessionId: 12 }),
    )

    expect(markup).toContain('Divergence avec la correction officielle UNESS')
    expect(markup).toContain('Le cours local contredit la correction officielle.')
    expect(markup).toContain('Correction officielle UNESS')
    expect(markup).toContain('Réponse officielle')
    expect(markup).toContain('https://entrainement.uness.example/review/42')
    expect(markup).toContain('Université Paris Cité')
    expect(markup).toContain('DFASM3')
    expect(markup).toContain('2026')
    expect(markup).toContain('2026-07-30T09:15:00+02:00')
    expect(markup).toContain('complete')
  })

  it('warns that an unsupported visual question has no AI verdict', () => {
    const payload: SessionPayload = {
      session: { id: 12, total_questions: 1, course_title: 'Gériatrie' },
      questions: [
        {
          id: 7,
          prompt: 'Interprète ce support visuel :',
          choices: ['A', 'B'],
          question_kind: 'closed',
          uness: {
            ...unessQuestion,
            question: {
              ...unessQuestion.question,
              verification_status: 'unsupported',
              support_visuel_seul: false,
              images: unessQuestion.question.images.map((image) => ({
                ...image,
                metadata: { verification_status: 'unsupported' },
              })),
            },
          },
        },
      ],
      answers: {},
    }

    const markup = renderToStaticMarkup(
      createElement(components.Reader, { payload, onCorrection: () => undefined }),
    )

    expect(markup).toContain('Vérification IA visuelle indisponible')
    expect(markup).toContain('Aucun verdict IA')
  })

  it('keeps the divergence warning visible while a correct row is collapsed', () => {
    const row: CorrectionRow = {
      position: 1,
      status: 'correct',
      response: 'Réponse IA',
      correct_answer: '["Réponse IA"]',
      explanation: 'Explication IA indépendante.',
      choices: ['Réponse IA', 'Réponse officielle'],
      question: {
        id: 7,
        prompt: 'Concernant le delirium :',
        choices: ['Réponse IA', 'Réponse officielle'],
        question_kind: 'closed',
        uness: unessQuestion,
      },
    }

    const markup = renderToStaticMarkup(
      createElement(components.CorrectionCard, { row, sessionId: 12 }),
    )

    expect(markup).toContain('Divergence UNESS')
  })
})
