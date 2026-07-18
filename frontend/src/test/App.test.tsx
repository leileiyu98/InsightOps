import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../App'
import type { QueryResponse } from '../types/query'

const executableResponse: QueryResponse = {
  request_id: 'req-001',
  question: '2025 年第二季度每个月的 SaaS Revenue 是多少？',
  action: 'execute_sql',
  generated_sql: 'SELECT report_month, saas_revenue\nFROM monthly_revenue',
  clarification_code: null,
  clarification_question: null,
  evaluation_status: 'PASS',
  failure_code: null,
  columns: ['report_month', 'saas_revenue'],
  rows: [
    { report_month: '2025-04', saas_revenue: '12800.0000' },
    { report_month: '2025-05', saas_revenue: null },
  ],
  business_summary: 'The query returned two monthly revenue observations.',
  provider: 'fake',
  model: 'deterministic-v1',
}

const clarificationResponse: QueryResponse = {
  request_id: 'req-002',
  question: 'Marketing ROAS 应该使用哪一种收入定义？',
  action: 'request_clarification',
  generated_sql: null,
  clarification_code: 'attributed_revenue_type_required',
  clarification_question: '请明确 ROAS 使用 SaaS Revenue 还是 Commerce Revenue？',
  evaluation_status: 'PASS',
  failure_code: null,
  columns: [],
  rows: [],
  business_summary: null,
  provider: 'fake',
  model: 'deterministic-v1',
}

const healthResponse = () => jsonResponse({ status: 'ok' })

describe('InsightOps demo UI', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(healthResponse()))
  })

  it('renders the initial analytics workspace and reports API online', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: /Ask a business question/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Business question')).toHaveValue('')
    expect(screen.getAllByRole('button', { name: /Monthly revenue|GMV & order metrics|Clarify ROAS|Organization sample/ })).toHaveLength(4)
    expect(await screen.findByText('API Online')).toBeInTheDocument()
    expect(screen.getByText('Your evaluated answer will appear here')).toBeInTheDocument()
  })

  it('fills and clears a reviewed example without auto-submitting', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: /Monthly revenue/ }))

    expect(screen.getByLabelText('Business question')).toHaveValue(
      '2025 年第二季度每个月的 SaaS Revenue 是多少？',
    )
    expect(screen.getByLabelText(/Evaluation case ID/)).toHaveValue('GQ-SAA-002')
    expect(fetch).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: 'Clear' }))
    expect(screen.getByLabelText('Business question')).toHaveValue('')
    expect(screen.getByLabelText(/Evaluation case ID/)).toHaveValue('')
  })

  it('does not submit an empty question', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Run query' }))

    expect(screen.getByLabelText('Business question')).toBeInvalid()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('renders executable SQL, evaluation, table, summary, and null values', async () => {
    const user = userEvent.setup()
    mockQueryResponse(executableResponse)
    render(<App />)

    await user.click(screen.getByRole('button', { name: /Monthly revenue/ }))
    await user.click(screen.getByRole('button', { name: 'Run query' }))

    expect(await screen.findByText('PASS')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Generated SQL' })).toBeInTheDocument()
    expect(screen.getByText(/SELECT report_month/)).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText('12800.0000')).toBeInTheDocument()
    expect(within(table).getByText('NULL')).toBeInTheDocument()
    expect(screen.getByText('2 rows')).toBeInTheDocument()
    expect(screen.getByText(executableResponse.business_summary!)).toBeInTheDocument()
  })

  it('renders clarification without SQL or result table', async () => {
    const user = userEvent.setup()
    mockQueryResponse(clarificationResponse)
    render(<App />)

    await user.click(screen.getByRole('button', { name: /Clarify ROAS/ }))
    await user.click(screen.getByRole('button', { name: 'Run query' }))

    expect(await screen.findByText(clarificationResponse.clarification_question!)).toBeInTheDocument()
    expect(screen.getByText('attributed_revenue_type_required')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Generated SQL' })).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows an unscored free query and omits case_id from the request body', async () => {
    const user = userEvent.setup()
    mockQueryResponse({
      ...executableResponse,
      request_id: 'req-free',
      question: '列出一个企业名称',
      generated_sql: 'SELECT organization_name FROM organization LIMIT 1',
      evaluation_status: 'not_benchmark_scored',
      columns: ['organization_name'],
      rows: [{ organization_name: 'Northstar Labs' }],
      business_summary: 'The first organization is Northstar Labs.',
    })
    render(<App />)

    await user.click(screen.getByRole('button', { name: /Organization sample/ }))
    await user.click(screen.getByRole('button', { name: 'Run query' }))

    expect(await screen.findByText('not_benchmark_scored')).toBeInTheDocument()
    const queryCall = vi.mocked(fetch).mock.calls[1]
    const init = queryCall?.[1]
    const requestBody = init?.body
    if (typeof requestBody !== 'string') throw new Error('Expected a JSON request body')
    expect(JSON.parse(requestBody)).toEqual({ question: '列出一个企业名称' })
  })

  it('shows a stable provider error with request ID', async () => {
    const user = userEvent.setup()
    vi.mocked(fetch)
      .mockResolvedValueOnce(healthResponse())
      .mockResolvedValueOnce(
        jsonResponse(
          { request_id: 'error-001', code: 'provider_unavailable', message: 'stable' },
          502,
        ),
      )
    render(<App />)

    await user.click(screen.getByRole('button', { name: /Monthly revenue/ }))
    await user.click(screen.getByRole('button', { name: 'Run query' }))

    expect(await screen.findByText(/configured query provider is temporarily unavailable/)).toBeInTheDocument()
    expect(screen.getByText('Request ID: error-001')).toBeInTheDocument()
  })

  it('disables duplicate submission while a query is loading', async () => {
    const user = userEvent.setup()
    let resolveQuery: ((response: Response) => void) | undefined
    const pendingQuery = new Promise<Response>((resolve) => {
      resolveQuery = resolve
    })
    vi.mocked(fetch)
      .mockResolvedValueOnce(healthResponse())
      .mockReturnValueOnce(pendingQuery)
    render(<App />)

    await user.click(screen.getByRole('button', { name: /Monthly revenue/ }))
    await user.click(screen.getByRole('button', { name: 'Run query' }))

    const loadingButton = screen.getByRole('button', { name: /Running query/ })
    expect(loadingButton).toBeDisabled()
    await user.click(loadingButton)
    expect(fetch).toHaveBeenCalledTimes(2)

    resolveQuery?.(jsonResponse(executableResponse))
    expect(await screen.findByText('PASS')).toBeInTheDocument()
  })

  it('copies generated SQL with visible feedback', async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    mockQueryResponse(executableResponse)
    render(<App />)

    await user.click(screen.getByRole('button', { name: /Monthly revenue/ }))
    await user.click(screen.getByRole('button', { name: 'Run query' }))
    await user.click(await screen.findByRole('button', { name: 'Copy SQL' }))

    expect(writeText).toHaveBeenCalledWith(executableResponse.generated_sql)
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('rejects a malformed successful response', async () => {
    const user = userEvent.setup()
    vi.mocked(fetch)
      .mockResolvedValueOnce(healthResponse())
      .mockResolvedValueOnce(jsonResponse({ request_id: 'req-bad', action: 'execute_sql' }))
    render(<App />)

    await user.click(screen.getByRole('button', { name: /Monthly revenue/ }))
    await user.click(screen.getByRole('button', { name: 'Run query' }))

    expect(await screen.findByText(/could not safely interpret/)).toBeInTheDocument()
  })

  it('loads normally when the API health check is offline', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('network'))
    render(<App />)

    expect(await screen.findByText('API Offline')).toBeInTheDocument()
    expect(screen.getByLabelText('Business question')).toBeEnabled()
  })
})

function mockQueryResponse(response: QueryResponse) {
  vi.mocked(fetch)
    .mockResolvedValueOnce(healthResponse())
    .mockResolvedValueOnce(jsonResponse(response))
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
