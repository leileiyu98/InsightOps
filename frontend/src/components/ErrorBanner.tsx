import type { QueryApiError } from '../api/query'

interface ErrorBannerProps {
  error: QueryApiError
}

const SAFE_MESSAGES: Record<string, string> = {
  api_unreachable: 'The API is unreachable. Confirm the FastAPI server is running and try again.',
  request_timeout: 'The request timed out before a result was available. Please try again.',
  provider_unavailable: 'The configured query provider is temporarily unavailable.',
  provider_not_configured: 'The query provider is not configured for this environment.',
  provider_timeout: 'The query provider did not respond before the server timeout.',
  provider_rate_limited: 'The query provider is rate limited. Please retry later.',
  provider_authentication_failed: 'The query provider could not authenticate.',
  evaluation_unavailable: 'The deterministic evaluation service is unavailable.',
  dataset_verification_failed: 'The demo dataset could not be verified.',
  case_not_found: 'That evaluation case ID does not exist.',
  case_not_available: 'That evaluation case is not available for this demo.',
  fake_candidate_not_configured: 'The offline provider does not support that demo question.',
  request_validation_error: 'Check the question and case ID, then try again.',
  malformed_response: 'The API returned a response that this UI could not safely interpret.',
  application_error: 'The server could not complete the request.',
}

export function ErrorBanner({ error }: ErrorBannerProps) {
  return (
    <section className="error-banner" role="alert" aria-live="assertive">
      <div className="error-banner__icon" aria-hidden="true">!</div>
      <div>
        <span className="step-label">REQUEST FAILED · {error.code}</span>
        <h2>We couldn’t complete this query</h2>
        <p>{SAFE_MESSAGES[error.code] ?? SAFE_MESSAGES.application_error}</p>
        {error.requestId ? <p className="error-banner__request">Request ID: {error.requestId}</p> : null}
      </div>
    </section>
  )
}
