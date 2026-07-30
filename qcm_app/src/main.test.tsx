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
    dp_context: { text: 'Une personne âgée présente une confusion aiguë.' },
  },
  question: {
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
