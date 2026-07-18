import { useCallback, useEffect, useRef, useState } from 'react'
import { getHealth, QueryApiError, submitQuery } from './api/query'
import { BusinessSummary } from './components/BusinessSummary'
import { ClarificationPanel } from './components/ClarificationPanel'
import { ErrorBanner } from './components/ErrorBanner'
import { ExampleQueries } from './components/ExampleQueries'
import { Header } from './components/Header'
import { QueryForm } from './components/QueryForm'
import { ResultTable } from './components/ResultTable'
import { SqlPanel } from './components/SqlPanel'
import { StatusPanel } from './components/StatusPanel'
import type { HealthStatus, QueryRequest, QueryResponse } from './types/query'

export function App() {
  const [question, setQuestion] = useState('')
  const [caseId, setCaseId] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [healthStatus, setHealthStatus] = useState<HealthStatus>('checking')
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [error, setError] = useState<QueryApiError | null>(null)
  const requestController = useRef<AbortController | null>(null)
  const requestSequence = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    void getHealth(controller.signal).then((online) => {
      if (!controller.signal.aborted) {
        setHealthStatus(online ? 'online' : 'offline')
      }
    })
    return () => controller.abort()
  }, [])

  useEffect(() => () => requestController.current?.abort(), [])

  const runQuery = useCallback(async () => {
    const trimmedQuestion = question.trim()
    if (!trimmedQuestion) {
      setError(new QueryApiError('request_validation_error', 'A question is required.'))
      return
    }

    requestController.current?.abort()
    const controller = new AbortController()
    requestController.current = controller
    const sequence = ++requestSequence.current
    setIsLoading(true)
    setError(null)

    const payload: QueryRequest = { question: trimmedQuestion }
    const trimmedCaseId = caseId.trim()
    if (trimmedCaseId) payload.case_id = trimmedCaseId

    try {
      const response = await submitQuery(payload, controller.signal)
      if (sequence === requestSequence.current) {
        setResult(response)
      }
    } catch (caught: unknown) {
      if (
        sequence === requestSequence.current &&
        caught instanceof QueryApiError &&
        caught.code !== 'request_cancelled'
      ) {
        setError(caught)
      }
    } finally {
      if (sequence === requestSequence.current) {
        setIsLoading(false)
        requestController.current = null
      }
    }
  }, [caseId, question])

  const clear = () => {
    requestController.current?.abort()
    requestController.current = null
    requestSequence.current += 1
    setQuestion('')
    setCaseId('')
    setResult(null)
    setError(null)
    setIsLoading(false)
  }

  const selectExample = (exampleQuestion: string, exampleCaseId?: string) => {
    setQuestion(exampleQuestion)
    setCaseId(exampleCaseId ?? '')
    setError(null)
  }

  return (
    <>
      <Header healthStatus={healthStatus} />
      <main id="main-content" className="page-shell">
        <section className="composer-layout" aria-label="Query workspace">
          <QueryForm
            question={question}
            caseId={caseId}
            isLoading={isLoading}
            onQuestionChange={setQuestion}
            onCaseIdChange={setCaseId}
            onSubmit={() => void runQuery()}
            onClear={clear}
          />
          <ExampleQueries disabled={isLoading} onSelect={selectExample} />
        </section>

        <div className="request-announcer" aria-live="polite">
          {isLoading ? 'Running query. Please wait.' : ''}
        </div>

        <section className="output" aria-label="Analysis output">
          {error ? <ErrorBanner error={error} /> : null}
          {result ? (
            <div className="output__content">
              <StatusPanel result={result} />
              {result.action === 'execute_sql' ? (
                <>
                  <SqlPanel sql={result.generated_sql ?? ''} />
                  <ResultTable columns={result.columns} rows={result.rows} />
                  <BusinessSummary summary={result.business_summary} />
                </>
              ) : (
                <ClarificationPanel
                  code={result.clarification_code ?? '—'}
                  question={result.clarification_question ?? 'Please clarify your request.'}
                />
              )}
            </div>
          ) : !error ? (
            <div className="empty-state empty-state--initial">
              <div className="empty-state__visual" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
              <strong>Your evaluated answer will appear here</strong>
              <span>Choose a reviewed demo or compose a business question above.</span>
            </div>
          ) : null}
        </section>
      </main>
      <footer className="footer">
        <span>InsightOps · M1.4 Demo UI</span>
        <span>Offline-first · Readonly by design</span>
      </footer>
    </>
  )
}
