interface ClarificationPanelProps {
  code: string
  question: string
}

export function ClarificationPanel({ code, question }: ClarificationPanelProps) {
  return (
    <section className="card clarification" aria-labelledby="clarification-title">
      <div className="clarification__icon" aria-hidden="true">?</div>
      <div>
        <span className="step-label">INPUT NEEDED</span>
        <h2 id="clarification-title">One detail needs clarification</h2>
        <p>{question}</p>
        <div className="clarification__code">
          <span>Clarification code</span>
          <code>{code}</code>
        </div>
        <p className="clarification__hint">
          Refine the business question with the requested definition, then run it again.
        </p>
      </div>
    </section>
  )
}
