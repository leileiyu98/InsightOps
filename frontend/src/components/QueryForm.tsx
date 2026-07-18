import type { FormEvent, KeyboardEvent } from 'react'

interface QueryFormProps {
  question: string
  caseId: string
  isLoading: boolean
  onQuestionChange: (value: string) => void
  onCaseIdChange: (value: string) => void
  onSubmit: () => void
  onClear: () => void
}

export function QueryForm({
  question,
  caseId,
  isLoading,
  onQuestionChange,
  onCaseIdChange,
  onSubmit,
  onClear,
}: QueryFormProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit()
  }

  const handleQuestionKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault()
      onSubmit()
    }
  }

  return (
    <form className="query-form" onSubmit={handleSubmit} aria-labelledby="composer-title">
      <div className="section-heading">
        <div>
          <span className="step-label">01 · COMPOSE</span>
          <h2 id="composer-title">What do you want to understand?</h2>
        </div>
        <span className="shortcut-hint">⌘ / Ctrl + Enter to run</span>
      </div>

      <label className="field-label" htmlFor="question">
        Business question
      </label>
      <textarea
        id="question"
        name="question"
        rows={5}
        maxLength={4000}
        placeholder="Ask about revenue, growth, orders, or marketing performance…"
        value={question}
        disabled={isLoading}
        onChange={(event) => onQuestionChange(event.target.value)}
        onKeyDown={handleQuestionKeyDown}
        required
      />

      <div className="query-form__footer">
        <div className="case-field">
          <label className="field-label" htmlFor="case-id">
            Evaluation case ID <span>Optional</span>
          </label>
          <input
            id="case-id"
            name="case-id"
            type="text"
            placeholder="e.g. GQ-SAA-002"
            value={caseId}
            disabled={isLoading}
            onChange={(event) => onCaseIdChange(event.target.value)}
            autoComplete="off"
          />
        </div>
        <div className="form-actions">
          <button className="button button--secondary" type="button" onClick={onClear}>
            Clear
          </button>
          <button className="button button--primary" type="submit" disabled={isLoading}>
            {isLoading ? (
              <>
                <span className="spinner" aria-hidden="true" />
                Running query
              </>
            ) : (
              <>
                Run query
                <svg viewBox="0 0 18 18" aria-hidden="true">
                  <path d="M4 9h10M10 5l4 4-4 4" />
                </svg>
              </>
            )}
          </button>
        </div>
      </div>
    </form>
  )
}
