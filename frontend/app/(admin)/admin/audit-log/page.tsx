"use client";

import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { HorizontalPagination } from "@/components/ui/HorizontalPagination";
import { SystemFeedback } from "@/components/ui/SystemFeedback";

type AuditEntry = {
  id: number;
  actor_id: number;
  actor_name: string;
  action: string;
  entity_type: string;
  entity_id: number;
  details: string;
  created_at: string;
};

type AuditResponse = { items: AuditEntry[]; total: number };

export default function Page() {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ actor_id: "", entity: "", date_from: "", date_to: "" });
  const [error, setError] = useState("");

  const load = useCallback(async (nextPage = 1) => {
    try {
      const query = new URLSearchParams({ page: String(nextPage) });
      Object.entries(filters).forEach(([key, value]) => value && query.set(key, value));
      const { data } = await api.get<AuditResponse>(`/api/v1/audit-logs?${query}`);
      setRows(data.items);
      setTotal(data.total);
      setPage(nextPage);
      setError("");
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "Unable to load audit logs.");
    }
  }, [filters]);

  useEffect(() => { void load(); }, [load]);

  function updateFilter(key: keyof typeof filters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return <div className="max-w-7xl">
    <h1 className="mb-6 text-3xl font-bold">Audit log</h1>
    <div className="mb-5 grid gap-3 md:grid-cols-4">
      <input placeholder="Actor ID" value={filters.actor_id} onChange={(event) => updateFilter("actor_id", event.target.value)} />
      <input placeholder="Entity type" value={filters.entity} onChange={(event) => updateFilter("entity", event.target.value)} />
      <input type="date" value={filters.date_from} onChange={(event) => updateFilter("date_from", event.target.value)} />
      <input type="date" value={filters.date_to} onChange={(event) => updateFilter("date_to", event.target.value)} />
    </div>
    {error && <SystemFeedback className="mb-3" tone="danger" title="Unable to load audit log" description={error} />}
    <div className="table-wrap">
      <table>
        <thead><tr><th>Timestamp</th><th>Actor</th><th>Action</th><th>Entity</th><th>Before / after</th></tr></thead>
        <tbody>
          {rows.map((entry) => <tr key={entry.id} className="align-top">
            <td className="whitespace-nowrap">{new Date(entry.created_at).toLocaleString()}</td>
            <td>{entry.actor_name}<br /><span className="text-slate-500">#{entry.actor_id}</span></td>
            <td>{entry.action}</td>
            <td>{entry.entity_type} #{entry.entity_id}</td>
            <td className="max-w-md break-all text-slate-300">{entry.details}</td>
          </tr>)}
          {!rows.length && <tr><td colSpan={5} className="p-5 text-center text-slate-400">No audit entries match the filters.</td></tr>}
        </tbody>
      </table>
      <HorizontalPagination page={page} total={total} pageSize={50} onPageChange={(nextPage) => void load(nextPage)} />
    </div>
  </div>;
}
