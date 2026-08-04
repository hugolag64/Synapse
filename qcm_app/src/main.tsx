import { Component, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { completeSession, fetchSession, followUpAction, replaySession, saveAttempt } from './api'
import type { CorrectionPayload, CorrectionRow, Question, SessionPayload, UnessImage } from './types'
import { MedicalImageViewer } from './components/MedicalImageViewer'
import './styles.css'

const sessionId = Number(new URLSearchParams(window.location.search).get('session'))

function Header({ onExit = false }: { onExit?: boolean }) {
  return <header className="brand"><div className="brand-lockup"><span className="brand-mark">S</span><strong>Synapse</strong><span className="brand-slash">/</span><span>QCM</span></div>{onExit && <button className="exit-session" onClick={() => { window.location.href = '/qcm' }}>Quitter la session</button>}</header>
}

class RenderBoundary extends Component<React.PropsWithChildren, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) return <main className="state"><Header /><h1>Impossible d’ouvrir ce QCM</h1><p>{this.state.error.message}</p></main>
    return this.props.children
  }
}

export function contextText(context: Record<string, unknown> | undefined): string {
  if (!context) return ''
  const hiddenKeys = new Set(['dossier_id', 'dossier_number', 'dossier_type'])
  return Object.entries(context)
    .filter(([key]) => !hiddenKeys.has(key))
    .map(([, value]) => value)
    .flatMap((value) => {
      if (typeof value === 'string' || typeof value === 'number') return [String(value)]
      return []
    })
    .filter(Boolean)
    .join(' · ')
}

function imageSource(sessionId: number, questionId: number, index: number, image: UnessImage): string {
  if (image.local_path) return `/api/qcm/sessions/${sessionId}/questions/${questionId}/images/${index}`
  return image.source_url
}

function UnessProvenance({ question }: { question: Question }) {
  const exam = question.uness?.exam
  const provenance = question.uness?.provenance
  const identity = [exam?.faculty, exam?.level, exam?.year].filter((value) => value != null && value !== '')
  if (!identity.length && !provenance?.source_url && !provenance?.collected_at && !provenance?.collection_status) return null
  return <section className="uness-provenance">
    <strong>Provenance UNESS</strong>
    {identity.length > 0 && <span>{identity.join(' · ')}</span>}
    {provenance?.source_url && <a href={provenance.source_url} target="_blank" rel="noreferrer">{provenance.source_url}</a>}
    {(provenance?.collected_at || provenance?.collection_status) && <span>Collecté le {provenance.collected_at || '—'} · Statut : {provenance.collection_status || '—'}</span>}
  </section>
}

function QuestionVisualContext({ question, sessionId }: { question: Question; sessionId: number }) {
  const examContext = contextText(question.uness?.exam?.dp_context)
  const questionContext = contextText(question.uness?.question?.dp_context)
  const images = question.uness?.question?.images || []
  const contexts = [...new Set([examContext, questionContext].filter(Boolean))]
  const hasProvenance = Boolean(question.uness?.provenance || question.uness?.exam)
  const visualVerificationUnsupported = question.uness?.question?.verification_status === 'unsupported'
    || images.some((image) => image.metadata?.verification_status === 'unsupported')
  if (!contexts.length && !images.length && !question.uness?.question?.support_visuel_seul && !hasProvenance && !visualVerificationUnsupported) return null
  return <div className="uness-context">
    <UnessProvenance question={question} />
    {contexts.length > 0 && <section className="clinical-context"><strong>Contexte du dossier</strong>{contexts.map((context) => <p key={context}>{context}</p>)}</section>}
    {images.length > 0 && <div className="question-images">{images.map((image, index) => (
      <MedicalImageViewer
        key={`${image.source_url}-${index}`}
        src={imageSource(sessionId, question.id, index, image)}
        alt={image.alt_text || image.caption || `Support visuel ${index + 1}`}
        caption={image.caption || image.alt_text}
      />
    ))}</div>}
    {visualVerificationUnsupported && <div className="visual-warning" role="alert"><strong>Vérification IA visuelle indisponible</strong><span>Aucun verdict IA n’a été retenu pour cette question : un ou plusieurs supports visuels n’ont pas pu être fournis au modèle.</span></div>}
    {question.uness?.question?.support_visuel_seul && <div className="visual-warning" role="alert"><strong>Support visuel uniquement</strong><span>L’interaction UNESS originale n’est pas reconstruite ; utilise l’image comme support pédagogique.</span></div>}
  </div>
}

export function Reader({ payload, onCorrection }: { payload: SessionPayload; onCorrection: (value: CorrectionPayload) => void }) {
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState(payload.answers)
  const [busy, setBusy] = useState(false)
  const isExamParam = new URLSearchParams(window.location.search).get('exam') === '1'
  const [examMode, setExamMode] = useState(isExamParam)
  
  // Mode Concours / Chronomètre (ex: 2 min par question par défaut)
  const totalSeconds = useMemo(() => payload.questions.length * 120, [payload.questions.length])
  const [timeLeft, setTimeLeft] = useState(totalSeconds)

  useEffect(() => {
    if (!examMode) return
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer)
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [examMode])

  const question = payload.questions[index]
  if (!question) return <main className="state"><Header /><h1>QCM vide</h1><p>Cette session ne contient aucune question.</p></main>

  const isQroc = question.question_kind === 'open' || question.choices.length === 0 || question.uness?.question?.support_visuel_seul || question.uness?.question?.type_question === 'QROC'
  
  const selected = useMemo(() => {
    if (isQroc) return []
    try { return JSON.parse(answers[String(question.id)] || '[]') as string[] } catch { return [] }
  }, [answers, question.id, isQroc])

  const textAnswer = useMemo(() => {
    if (!isQroc) return ''
    return answers[String(question.id)] || ''
  }, [answers, question.id, isQroc])

  function toggle(choice: string) {
    const next = selected.includes(choice) ? selected.filter((item) => item !== choice) : [...selected, choice]
    setAnswers({ ...answers, [String(question.id)]: JSON.stringify(next) })
  }

  function handleTextChange(val: string) {
    setAnswers({ ...answers, [String(question.id)]: val })
  }

  async function next() {
    setBusy(true)
    const response = answers[String(question.id)] || ''
    await saveAttempt(payload.session.id, question.id, response)
    if (index < payload.questions.length - 1) setIndex(index + 1)
    else onCorrection(await completeSession(payload.session.id))
    setBusy(false)
  }

  const formatTimer = (seconds: number) => {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }

  return <main className="reader-page">
    <Header onExit />
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '8px 0' }}>
      {isExamParam ? (
        <span style={{ fontSize: '12px', fontWeight: 800, letterSpacing: '0.08em', color: '#e5484d', textTransform: 'uppercase', background: '#ffeef0', padding: '4px 10px', borderRadius: '6px' }}>
          🔒 Mode Examen Blanc — Anti-Retour Actif
        </span>
      ) : (
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', color: '#a0a0ab' }}>
          <input
            type="checkbox"
            checked={examMode}
            onChange={(e) => setExamMode(e.target.checked)}
          />
          <span>Activer le mode Concours Blanc (Chronomètre & épreuve fermée)</span>
        </label>
      )}
      {examMode && (
        <div className="timer-bar" style={{ margin: 0 }}>
          <span className="timer-label">⏱ CHRONO</span>
          <span className={`timer-clock ${timeLeft < 180 ? 'warning' : ''}`}>{formatTimer(timeLeft)}</span>
        </div>
      )}
    </div>
    <div className="reader-kicker">{isExamParam ? 'CONCOURS BLANC' : 'SESSION QCM'} · ITEM {payload.session.item_number || '—'}</div>
    <h1>{payload.session.course_title || 'Session Examen'}</h1>
    <p className="reader-subtitle">{isExamParam ? 'Réponds à chaque question dans l’ordre sans possibilité de retour en arrière.' : 'Réponds aux questions, puis consulte ta correction détaillée.'}</p>
    <div className="progress-line"><span style={{ width: `${((index + 1) / payload.questions.length) * 100}%` }} /></div>
    <div className="reader-meta">Question {index + 1} sur {payload.questions.length}</div>
    <section className="question-card">
      <QuestionVisualContext question={question} sessionId={payload.session.id} />
      <h2 className="question-prompt">{question.prompt}</h2>
      
      {isQroc ? (
        <div className="qroc-container">
          <p className="answer-hint">Réponse ouverte / QROC / Zone à désigner (saisie libre) :</p>
          <textarea
            className="qroc-input"
            rows={4}
            placeholder="Tape ta réponse ou désigne la structure anatomique/zone visuelle..."
            value={textAnswer}
            onChange={(e) => handleTextChange(e.target.value)}
          />
        </div>
      ) : (
        <>
          <p className="answer-hint">Plusieurs réponses possibles</p>
          <div className="choices">
            {question.choices.map((choice, choiceIndex) => <button className={`choice ${selected.includes(choice) ? 'selected' : ''}`} key={choice} onClick={() => toggle(choice)}>
              <span className="choice-letter">{String.fromCharCode(65 + choiceIndex)}</span><span>{choice}</span><span className="choice-check">{selected.includes(choice) ? '✓' : ''}</span>
            </button>)}
          </div>
        </>
      )}
    </section>
    <footer className="reader-actions">
      {!isExamParam && (
        <button className="button secondary" onClick={() => index && setIndex(index - 1)} disabled={!index}>Précédente</button>
      )}
      <button className="button primary" onClick={next} disabled={busy}>{index === payload.questions.length - 1 ? 'Valider et terminer l’épreuve' : 'Valider & Question suivante 🔒'}</button>
    </footer>
  </main>
}

export function Correction({ payload, onReplay }: { payload: CorrectionPayload; onReplay: (id: number) => void }) {
  const [errorsOnly, setErrorsOnly] = useState(false)
  const [followUp, setFollowUp] = useState(payload.follow_up)
  const rows = errorsOnly ? payload.rows.filter((row) => row.status !== 'correct') : payload.rows
  const scorePercent = payload.session.score_percent == null ? 0 : payload.session.score_percent
  const score20 = ((scorePercent / 100) * 20).toFixed(1)

  const followUpCard = followUp && <section className="follow-up"><div><strong>Plusieurs échecs sur ce contexte</strong><p>{followUp.failure_streak} sessions sous 70 %. Veux-tu transformer cette difficulté en support de révision ?</p></div><div className="follow-up-actions"><button className="button secondary" onClick={async () => { await followUpAction(payload.session.id, 'anchor', followUp.question_id); setFollowUp(null) }}>Ancrer la question</button><button className="button primary" onClick={async () => { await followUpAction(payload.session.id, 'lacune'); setFollowUp(null) }}>Créer une fiche lacune</button><button className="button quiet" onClick={async () => { await followUpAction(payload.session.id, 'ignore'); setFollowUp(null) }}>Ignorer</button></div></section>
  return <main className="correction-page">{followUpCard}
    <Header onExit />
    <div className="reader-kicker">CORRECTION TERMINÉE · {new Date().toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase()}</div>
    <h1>{payload.session.course_title || 'QCM'}</h1>
    <p className="reader-subtitle">Tu peux parcourir les erreurs, relire les explications et relancer ce QCM quand tu veux.</p>
    <div className="score-mode-banner"><strong>Barème EDN propositionnel</strong><span>Chaque question suit la grille 1 / 0,5 / 0,2 / 0.</span></div>
    <section className="kpis">
      <div>
        <strong>{score20} / 20</strong>
        <span>Note EDN</span>
      </div>
      <div><strong>{payload.session.correct_count || 0} / {payload.rows.length}</strong><span>bonnes réponses</span></div>
      <div><strong className="danger">{payload.session.incorrect_count || 0}</strong><span>à retravailler</span></div>
      <div><strong>{scorePercent}%</strong><span>score global</span></div>
    </section>
    <div className="details-heading"><h2>Détail des réponses <span>· {payload.rows.length} questions</span></h2><button className={`filter ${errorsOnly ? 'active' : ''}`} onClick={() => setErrorsOnly(!errorsOnly)}>Afficher uniquement mes erreurs</button></div>
    <div className="correction-list">{rows.map((row) => <CorrectionCard key={row.position} row={row} sessionId={payload.session.id} />)}</div>
    <footer className="correction-actions"><button className="button secondary" onClick={() => window.history.back()}>Retour à l’historique</button><button className="button primary" onClick={async () => onReplay(await replaySession(payload.session.id))}>Rejouer ce QCM</button></footer>
  </main>
}

export function CorrectionCard({ row, sessionId }: { row: CorrectionRow; sessionId: number }) {
  const [open, setOpen] = useState(row.status === 'incorrect')
  const correct = row.status === 'correct'
  const correction = row.correction || row.question.correction
  const disagreements = row.question.uness?.propositions?.filter((proposition) => proposition.statut === 'desaccord') || []
  const disagreementComments = correction?.disagreement?.comments?.length
    ? correction.disagreement.comments
    : disagreements.map((proposition) => proposition.commentaire_desaccord || '').filter(Boolean)
  const hasDisagreement = correction?.disagreement?.present || disagreements.length > 0
  const official = correction?.official
  return <article className={`correction-card ${correct ? 'is-correct' : 'is-error'}`}>
    <button className="correction-summary" onClick={() => setOpen(!open)}><span className="question-number">{row.position}</span><strong>{row.question.prompt}</strong><span className="status">● {correct ? 'Correcte' : row.status === 'unanswered' ? 'Sans réponse' : 'Incorrecte'}{hasDisagreement && <span className="divergence-badge">⚠ Divergence UNESS</span>}</span><span>{open ? '⌃' : '›'}</span></button>
    {open && <div className="correction-detail">
      <QuestionVisualContext question={row.question} sessionId={sessionId} />
      {hasDisagreement && <div className="uness-warning" role="alert"><strong>Divergence avec la correction officielle UNESS</strong>{disagreementComments.map((comment) => <p key={comment}>{comment}</p>)}</div>}
      <div className="correction-body"><div className="answers"><div className="answer-label">Ta réponse</div><p className="answer-wrong">{row.response || 'Aucune réponse'}</p><div className="answer-label">Réponse correcte</div><p className="answer-right">{row.correct_answer}</p>
        {official && <details className="official-correction"><summary>Correction officielle UNESS</summary><p>{official.answer.length ? official.answer.join(', ') : 'Non disponible'}{official.available ? '' : ' (partielle)'}</p></details>}
      </div><aside><h3>POURQUOI ?</h3><p>{row.explanation}</p></aside></div>
      {row.propositions && row.propositions.length > 0 && <section className="proposition-correction" aria-label="Détail des propositions">
        <h3>Détail propositionnel EDN</h3>
        <div className="proposition-list" role="list">
          {row.propositions.map((proposition) => <div className="proposition-line" role="listitem" key={proposition.proposition_id}>
            <strong>{proposition.proposition_id}{proposition.text ? ` · ${proposition.text}` : ''}</strong>
            <span>{Boolean(proposition.selected) ? 'Sélectionnée' : 'Non sélectionnée'}</span>
            <span>{Boolean(proposition.expected) ? 'Attendue' : 'Non attendue'}</span>
            {proposition.rank && <span>Rang {proposition.rank}</span>}
            <span>{proposition.points} pt · {proposition.discordance}</span>
          </div>)}
        </div>
      </section>}
    </div>}
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

export default function Root() {
  return <RenderBoundary><App /></RenderBoundary>
}

const root = document.getElementById('root')
if (!root) throw new Error('Point de montage QCM introuvable')
createRoot(root).render(<Root />)
