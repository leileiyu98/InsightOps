import type {
  EvaluationStatus,
  QueryErrorResponse,
  QueryRequest,
  QueryResponse,
  QueryScalar,
} from '../types/query'

const QUERY_TIMEOUT_MS = 30_000

const EVALUATION_STATUSES = new Set<EvaluationStatus>([
  'PASS',
  'not_benchmark_scored',
  'FAIL_ACTION',
  'FAIL_STRUCTURE',
  'FAIL_EXECUTION',
  'FAIL_RESULT',
  'NOT_EVALUATED',
  'ABORTED',
])

export class QueryApiError extends Error {
  readonly code: string
  readonly requestId: string | null
  readonly status: number | null

  constructor(
    code: string,
    message: string,
    options: { requestId?: string | null; status?: number | null } = {},
  ) {
    super(message)
    this.name = 'QueryApiError'
    this.code = code
    this.requestId = options.requestId ?? null
    this.status = options.status ?? null
  }
}

export async function submitQuery(
  payload: QueryRequest,
  signal?: AbortSignal,
): Promise<QueryResponse> {
  const controller = new AbortController()
  let didTimeout = false
  const abortFromCaller = () => controller.abort()
  signal?.addEventListener('abort', abortFromCaller, { once: true })
  const timeoutId = window.setTimeout(() => {
    didTimeout = true
    controller.abort()
  }, QUERY_TIMEOUT_MS)

  try {
    const response = await fetch('/v1/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    const body: unknown = await parseJson(response)

    if (!response.ok) {
      const error = parseErrorResponse(body)
      throw new QueryApiError(error.code, error.message, {
        requestId: error.request_id,
        status: response.status,
      })
    }

    if (!isQueryResponse(body)) {
      throw new QueryApiError(
        'malformed_response',
        'The API returned an unexpected response format.',
        { status: response.status },
      )
    }
    return body
  } catch (error: unknown) {
    if (error instanceof QueryApiError) {
      throw error
    }
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new QueryApiError(
        didTimeout ? 'request_timeout' : 'request_cancelled',
        didTimeout ? 'The query request timed out.' : 'The query request was cancelled.',
      )
    }
    throw new QueryApiError('api_unreachable', 'The API could not be reached.')
  } finally {
    window.clearTimeout(timeoutId)
    signal?.removeEventListener('abort', abortFromCaller)
  }
}

export async function getHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch('/health', { signal })
    if (!response.ok) return false
    const body: unknown = await parseJson(response)
    return isRecord(body) && body.status === 'ok'
  } catch {
    return false
  }
}

async function parseJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    throw new QueryApiError(
      'malformed_response',
      'The API returned an unexpected response format.',
      { status: response.status },
    )
  }
}

function parseErrorResponse(value: unknown): QueryErrorResponse {
  if (
    isRecord(value) &&
    typeof value.request_id === 'string' &&
    typeof value.code === 'string' &&
    typeof value.message === 'string'
  ) {
    return {
      request_id: value.request_id,
      code: value.code,
      message: value.message,
    }
  }
  return {
    request_id: '',
    code: 'application_error',
    message: 'The API could not complete the request.',
  }
}

function isQueryResponse(value: unknown): value is QueryResponse {
  if (!isRecord(value)) return false
  if (!Array.isArray(value.columns) || !Array.isArray(value.rows)) return false

  const commonFieldsAreValid =
    typeof value.request_id === 'string' &&
    typeof value.question === 'string' &&
    (value.action === 'execute_sql' || value.action === 'request_clarification') &&
    nullableString(value.generated_sql) &&
    nullableString(value.clarification_code) &&
    nullableString(value.clarification_question) &&
    typeof value.evaluation_status === 'string' &&
    EVALUATION_STATUSES.has(value.evaluation_status as EvaluationStatus) &&
    nullableString(value.failure_code) &&
    value.columns.every((column) => typeof column === 'string') &&
    value.rows.every(isQueryRow) &&
    nullableString(value.business_summary) &&
    typeof value.provider === 'string' &&
    typeof value.model === 'string'

  if (!commonFieldsAreValid) return false

  if (value.action === 'execute_sql') {
    return (
      typeof value.generated_sql === 'string' &&
      value.clarification_code === null &&
      value.clarification_question === null
    )
  }

  return (
    value.generated_sql === null &&
    typeof value.clarification_code === 'string' &&
    typeof value.clarification_question === 'string' &&
    value.columns.length === 0 &&
    value.rows.length === 0 &&
    value.business_summary === null
  )
}

function isQueryRow(value: unknown): value is Record<string, QueryScalar> {
  return isRecord(value) && Object.values(value).every(isQueryScalar)
}

function isQueryScalar(value: unknown): value is QueryScalar {
  return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
