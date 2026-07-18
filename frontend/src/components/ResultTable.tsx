import type { QueryScalar } from '../types/query'

interface ResultTableProps {
  columns: string[]
  rows: Record<string, QueryScalar>[]
}

export function ResultTable({ columns, rows }: ResultTableProps) {
  return (
    <section className="card table-card" aria-labelledby="results-title">
      <div className="card__heading">
        <div>
          <span className="step-label">04 · RESULT SET</span>
          <h2 id="results-title">Query results</h2>
        </div>
        <span className="row-count">
          {rows.length} {rows.length === 1 ? 'row' : 'rows'}
        </span>
      </div>
      {columns.length === 0 || rows.length === 0 ? (
        <div className="empty-state empty-state--compact">
          <strong>No rows returned</strong>
          <span>The query completed successfully with an empty result set.</span>
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column} scope="col">{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column) => {
                    const value = row[column] ?? null
                    return (
                      <td key={column} className={value === null ? 'null-value' : undefined}>
                        {formatCell(value)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function formatCell(value: QueryScalar): string {
  if (value === null) return 'NULL'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}
