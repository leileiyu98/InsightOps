interface BusinessSummaryProps {
  summary: string | null
}

export function BusinessSummary({ summary }: BusinessSummaryProps) {
  return (
    <section className="card summary-card" aria-labelledby="summary-title">
      <div className="summary-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M5 18V9M12 18V5M19 18v-6M3 21h18" />
        </svg>
      </div>
      <div>
        <span className="step-label">05 · BUSINESS SUMMARY</span>
        <h2 id="summary-title">What the data says</h2>
        {summary ? (
          <p>{summary}</p>
        ) : (
          <p className="muted">No business summary was available for this result.</p>
        )}
      </div>
    </section>
  )
}
