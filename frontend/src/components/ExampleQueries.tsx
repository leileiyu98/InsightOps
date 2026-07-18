interface DemoQuestion {
  category: string
  label: string
  question: string
  caseId?: string
}

interface ExampleQueriesProps {
  disabled: boolean
  onSelect: (question: string, caseId?: string) => void
}

const DEMO_QUESTIONS: DemoQuestion[] = [
  {
    category: 'SAAS',
    label: 'Monthly revenue',
    question: '2025 年第二季度每个月的 SaaS Revenue 是多少？',
    caseId: 'GQ-SAA-002',
  },
  {
    category: 'COMMERCE',
    label: 'GMV & order metrics',
    question: '2025 年 6 月的 GMV、订单数和 AOV 是多少？',
    caseId: 'GQ-COM-001',
  },
  {
    category: 'MARKETING',
    label: 'Clarify ROAS',
    question: 'Marketing ROAS 应该使用哪一种收入定义？',
    caseId: 'GQ-MKT-006',
  },
  {
    category: 'FREE QUERY',
    label: 'Organization sample',
    question: '列出一个企业名称',
  },
]

export function ExampleQueries({ disabled, onSelect }: ExampleQueriesProps) {
  return (
    <aside className="examples" aria-labelledby="examples-title">
      <div className="examples__heading">
        <div>
          <span className="step-label">DEMO LIBRARY</span>
          <h2 id="examples-title">Try a reviewed question</h2>
        </div>
        <span className="examples__count">04</span>
      </div>
      <div className="example-list">
        {DEMO_QUESTIONS.map((example) => (
          <button
            className="example"
            type="button"
            key={example.category}
            disabled={disabled}
            onClick={() => onSelect(example.question, example.caseId)}
          >
            <span className="example__meta">
              <span>{example.category}</span>
              <span>{example.caseId ?? 'UNSCORED'}</span>
            </span>
            <strong>{example.label}</strong>
            <span className="example__question">{example.question}</span>
            <svg viewBox="0 0 18 18" aria-hidden="true">
              <path d="M4 9h10M10 5l4 4-4 4" />
            </svg>
          </button>
        ))}
      </div>
      <p className="examples__note">
        Demo cases use the offline deterministic provider. No API key required.
      </p>
    </aside>
  )
}
