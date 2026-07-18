import type { HealthStatus } from '../types/query'

interface HeaderProps {
  healthStatus: HealthStatus
}

const CAPABILITIES = [
  'Structured LLM Output',
  'SQL AST Validation',
  'Readonly Execution',
  'Deterministic Evaluation',
]

export function Header({ healthStatus }: HeaderProps) {
  const healthLabel = {
    checking: 'Checking API',
    online: 'API Online',
    offline: 'API Offline',
  }[healthStatus]

  return (
    <header className="hero">
      <nav className="topbar" aria-label="Product">
        <a className="brand" href="#main-content" aria-label="InsightOps home">
          <span className="brand-mark" aria-hidden="true">
            IO
          </span>
          <span>InsightOps</span>
        </a>
        <span className={`health health--${healthStatus}`} role="status">
          <span className="health__dot" aria-hidden="true" />
          {healthLabel}
        </span>
      </nav>

      <div className="hero__content">
        <p className="eyebrow">EVALUATED TEXT-TO-SQL ANALYTICS COPILOT</p>
        <h1>Ask a business question.<br />Trust the path to the answer.</h1>
        <p className="hero__description">
          Translate natural language into governed, readonly analytics with every result
          evaluated against deterministic business truth.
        </p>
        <ul className="capabilities" aria-label="Product capabilities">
          {CAPABILITIES.map((capability) => (
            <li key={capability}>
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="m3.5 8.2 2.8 2.7 6.2-6.1" />
              </svg>
              {capability}
            </li>
          ))}
        </ul>
      </div>
    </header>
  )
}
