import { useEffect, useMemo, useState } from 'react'
import { completeSession, fetchSession, replaySession, saveAttempt } from './api'
import type { CorrectionPayload, CorrectionRow, SessionPayload } from './types'
import './styles.css'

const sessionId = Number(new URLSearchParams(window.location.search).get('session'))

function Header() {
  return <header className="brand"><span className="brand-mark">S</span><strong>Synapse</strong><span className="brand-slash">/</span><span>QCM</span></header>
}

function Reader({ payload, onCorrection }: { payload: SessionPayload; onCorrection: (value: CorrectionPayload) => void }) {
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState(payload.answers)
  const [busy, setBusy] = useState(false)
  const question = payload.questions[index]
  const selected = useMemo(() => {
    try { return JSON.parse(answers[String(question.id)] || '[]') as string[] } catch { return [] }
  }, [answers, question.id])

  function toggle(choice: string) {
    const next = selected.includes(choice) ? selected.filter((item) => item !== choice) : [...selected, choice]
    setAnswers({ ...answers, [String(question.id)]: JSON.stringify(next) })
  }

  async function next() {
    setBusy(true)
    const response = answers[String(question.id)] || ''
    await saveAttempt(payload.session.id, question.id, response)
    if (index < payload.questions.length - 1) setIndex(index + 1)
    else onCorrection(await completeSession(payload.session.id))
    setBusy(false)
  }

  return <main className="reader-page">
    <Header />
    <div className="reader-kicker">SESSION QCM · ITEM {payload.session.item_number || '—'}</div>
    <h1>{payload.session.course_title || 'Session QCM'}</h1>
    <p className="reader-subtitle">Réponds aux questions, puis consulte ta correction détaillée.</p>
    <div className="progress-line"><span style={{ width: `${((index + 1) / payload.questions.length) * 100}%` }} /></div>
    <div className="reader-meta">Question {index + 1} sur {payload.questions.length}</div>
    <section className="question-card">
      <h2>{question.prompt}</h2>
      <p className="answer-hint">Plusieurs réponses possibles</p>
      <div className="choices">
        {question.choices.map((choice, choiceIndex) => <button className={`choice ${selected.includes(choice) ? 'selected' : ''}`} key={choice} onClick={() => toggle(choice)}>
          <span className="choice-letter">{String.fromCharCode(65 + choiceIndex)}</span><span>{choice}</span><span className="choice-check">{selected.includes(choice) ? '✓' : ''}</span>
        </button>)}
      </div>
    </section>
    <footer className="reader-actions"><button className="button secondary" onClick={() => index && setIndex(index - 1)} disabled={!index}>Précédente</button><button className="button primary" onClick={next} disabled={busy}>{index === payload.questions.length - 1 ? 'Corriger mes réponses' : 'Suivante'}</button></footer>
  </main>
}

function Correction({ payload, onReplay }: { payload: CorrectionPayload; onReplay: (id: number) => void }) {
  const [errorsOnly, setErrorsOnly] = useState(false)
  const rows = errorsOnly ? payload.rows.filter((row) => row.status !== 'correct') : payload.rows
  const score = payload.session.score_percent == null ? '—' : `${payload.session.score_percent}%`
  return <main className="correction-page">
    <Header />
    <div className="reader-kicker">CORRECTION TERMINÉE · {new Date().toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase()}</div>
    <h1>{payload.session.course_title || 'QCM'}</h1>
    <p className="reader-subtitle">Tu peux parcourir les erreurs, relire les explications et relancer ce QCM quand tu veux.</p>
    <section className="kpis"><div><strong className="success">{score}</strong><span>score final</span></div><div><strong>{payload.session.correct_count || 0} / {payload.rows.length}</strong><span>bonnes réponses</span></div><div><strong className="danger">{payload.session.incorrect_count || 0}</strong><span>à retravailler</span></div><div><strong>—</strong><span>temps passé</span></div></section>
    <div className="details-heading"><h2>Détail des réponses <span>· {payload.rows.length} questions</span></h2><button className={`filter ${errorsOnly ? 'active' : ''}`} onClick={() => setErrorsOnly(!errorsOnly)}>Afficher uniquement mes erreurs</button></div>
    <div className="correction-list">{rows.map((row) => <CorrectionCard key={row.position} row={row} />)}</div>
    <footer className="correction-actions"><button className="button secondary" onClick={() => window.history.back()}>Retour à l’historique</button><button className="button primary" onClick={async () => onReplay(await replaySession(payload.session.id))}>Rejouer ce QCM</button></footer>
  </main>
}

function CorrectionCard({ row }: { row: CorrectionRow }) {
  const [open, setOpen] = useState(row.status === 'incorrect')
  const correct = row.status === 'correct'
  return <article className={`correction-card ${correct ? 'is-correct' : 'is-error'}`}>
    <button className="correction-summary" onClick={() => setOpen(!open)}><span className="question-number">{row.position}</span><strong>{row.question.prompt}</strong><span className="status">● {correct ? 'Correcte' : row.status === 'unanswered' ? 'Sans réponse' : 'Incorrecte'}</span><span>{open ? '⌃' : '›'}</span></button>
    {open && <div className="correction-body"><div className="answers"><div className="answer-label">Ta réponse</div><p className="answer-wrong">{row.response || 'Aucune réponse'}</p><div className="answer-label">Réponse correcte</div><p className="answer-right">{row.correct_answer}</p></div><aside><h3>POURQUOI ?</h3><p>{row.explanation}</p></aside></div>}
  </article>
}

function App() {
  const [data, setData] = useState<SessionPayload | CorrectionPayload | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { if (!sessionId) return setError('Session QCM manquante'); fetchSession(sessionId).then(setData).catch((reason) => setError(reason.message)) }, [])
  if (error) return <main className="state"><Header /><h1>Impossible d’ouvrir ce QCM</h1><p>{error}</p></main>
  if (!data) return <main className="state"><Header /><p>Chargement du QCM…</p></main>
  if ('rows' in data) return <Correction payload={data} onReplay={(id) => { window.location.search = `?session=${id}` }} />
  return <Reader payload={data} onCorrection={setData} />
}

export default App
