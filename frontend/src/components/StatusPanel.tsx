import type { QueryResponse } from '../types/query'

interface StatusPanelProps {
  result: QueryResponse
}

export function StatusPanel({ result }: StatusPanelProps) {
  const statusTone = getStatusTone(result.evaluation_status)
  return (
    <section className="card status-panel" aria-labelledby="status-title">
      <div className="card__heading">
        <div>
          <span className="step-label">02 · EVALUATION</span>
          <h2 id="status-title">Request summary</h2>
        </div>
        <span className={`status-badge status-badge--${statusTone}`}>
          <span aria-hidden="true" />
          {result.evaluation_status}
        </span>
      </div>
      <dl className="status-grid">
        <StatusItem term="Request ID" value={result.request_id} mono />
        <StatusItem term="Action" value={formatAction(result.action)} />
        <StatusItem term="Failure code" value={result.failure_code ?? '—'} mono />
        <StatusItem term="Provider" value={result.provider || '—'} />
        <StatusItem term="Model" value={result.model || '—'} />
      </dl>
    </section>
  )
}

function StatusItem({ term, value, mono = false }: { term: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt>{term}</dt>
      <dd className={mono ? 'mono-value' : undefined}>{value}</dd>
    </div>
  )
}

function formatAction(action: QueryResponse['action']) {
  return action === 'execute_sql' ? 'Execute SQL' : 'Request clarification'
}

function getStatusTone(status: string): 'success' | 'neutral' | 'danger' {
  if (status === 'PASS') return 'success'
  if (status === 'not_benchmark_scored') return 'neutral'
  return 'danger'
}
