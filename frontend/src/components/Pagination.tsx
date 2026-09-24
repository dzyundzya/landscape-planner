type Props = {
  currentPage: number
  pageSize: number
  totalItems: number
  ariaLabel: string
  onPageChange: (page: number) => void
}

export function Pagination({ currentPage, pageSize, totalItems, ariaLabel, onPageChange }: Props) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize))
  if (totalItems <= pageSize) return null

  const page = Math.min(Math.max(currentPage, 1), totalPages)
  const firstItem = (page - 1) * pageSize + 1
  const lastItem = Math.min(page * pageSize, totalItems)

  return (
    <nav className="pagination" aria-label={ariaLabel}>
      <span className="pagination-summary">{firstItem}–{lastItem} из {totalItems}</span>
      <div className="pagination-controls">
        <button
          type="button"
          aria-label="Предыдущая страница"
          disabled={page === 1}
          onClick={() => onPageChange(page - 1)}
        >
          ←
        </button>
        <label>
          <span className="sr-only">Текущая страница</span>
          <select value={page} onChange={(event) => onPageChange(Number(event.target.value))}>
            {Array.from({ length: totalPages }, (_, index) => index + 1).map((pageNumber) => (
              <option key={pageNumber} value={pageNumber}>{pageNumber}</option>
            ))}
          </select>
        </label>
        <span>из {totalPages}</span>
        <button
          type="button"
          aria-label="Следующая страница"
          disabled={page === totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          →
        </button>
      </div>
    </nav>
  )
}
