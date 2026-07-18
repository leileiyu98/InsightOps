import { useState } from 'react'

interface SqlPanelProps {
  sql: string
}

type CopyStatus = 'idle' | 'success' | 'error'

export function SqlPanel({ sql }: SqlPanelProps) {
  const [copyStatus, setCopyStatus] = useState<CopyStatus>('idle')

  const copySql = async () => {
    try {
      await navigator.clipboard.writeText(sql)
      setCopyStatus('success')
    } catch {
      setCopyStatus('error')
    }
  }

  return (
    <section className="card sql-panel" aria-labelledby="sql-title">
      <div className="card__heading card__heading--dark">
        <div>
          <span className="step-label">03 · GENERATED QUERY</span>
          <h2 id="sql-title">Generated SQL</h2>
        </div>
        <button className="copy-button" type="button" onClick={() => void copySql()}>
          <svg viewBox="0 0 18 18" aria-hidden="true">
            <rect x="6" y="6" width="8" height="8" rx="1" />
            <path d="M12 4V3.5A1.5 1.5 0 0 0 10.5 2h-7A1.5 1.5 0 0 0 2 3.5v7A1.5 1.5 0 0 0 3.5 12H4" />
          </svg>
          {copyStatus === 'success' ? 'Copied' : copyStatus === 'error' ? 'Copy failed' : 'Copy SQL'}
        </button>
      </div>
      <pre><code>{sql}</code></pre>
      <p className="sr-only" aria-live="polite">
        {copyStatus === 'success'
          ? 'SQL copied to clipboard.'
          : copyStatus === 'error'
            ? 'SQL could not be copied.'
            : ''}
      </p>
    </section>
  )
}
