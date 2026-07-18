export type QueryAction = 'execute_sql' | 'request_clarification'

export type EvaluationStatus =
  | 'PASS'
  | 'not_benchmark_scored'
  | 'FAIL_ACTION'
  | 'FAIL_STRUCTURE'
  | 'FAIL_EXECUTION'
  | 'FAIL_RESULT'
  | 'NOT_EVALUATED'
  | 'ABORTED'

export type QueryScalar = string | number | boolean | null

export interface QueryRequest {
  question: string
  case_id?: string
}

export interface QueryResponse {
  request_id: string
  question: string
  action: QueryAction
  generated_sql: string | null
  clarification_code: string | null
  clarification_question: string | null
  evaluation_status: EvaluationStatus
  failure_code: string | null
  columns: string[]
  rows: Record<string, QueryScalar>[]
  business_summary: string | null
  provider: string
  model: string
}

export interface QueryErrorResponse {
  request_id: string
  code: string
  message: string
}

export type HealthStatus = 'checking' | 'online' | 'offline'
