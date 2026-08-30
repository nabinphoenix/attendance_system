import { Button } from "./Button";

function visiblePageNumbers(page: number, totalPages: number) {
  const start = Math.max(1, Math.min(page - 2, totalPages - 4));
  return Array.from({ length: Math.min(5, totalPages) }, (_, index) => start + index);
}

export function HorizontalPagination({
  page,
  total,
  pageSize,
  onPageChange,
  disabled = false,
  className = "",
}: {
  page: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
  className?: string;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(page * pageSize, total);

  return <nav className={`flex flex-col gap-3 border-t border-slate-800 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6 ${className}`} aria-label="Pagination">
    <p className="app-caption text-sm">{total ? `Showing ${from}–${to} of ${total}` : "No results"}</p>
    <div className="flex flex-wrap items-center gap-1" aria-label="Page navigation">
      <Button type="button" variant="ghost" size="sm" disabled={disabled || page <= 1} onClick={() => onPageChange(page - 1)}>Previous</Button>
      {visiblePageNumbers(page, totalPages).map((number) => <Button key={number} type="button" size="sm" variant={number === page ? "primary" : "ghost"} aria-current={number === page ? "page" : undefined} disabled={disabled} onClick={() => onPageChange(number)}>{number}</Button>)}
      <Button type="button" variant="ghost" size="sm" disabled={disabled || page >= totalPages} onClick={() => onPageChange(page + 1)}>Next</Button>
    </div>
  </nav>;
}
