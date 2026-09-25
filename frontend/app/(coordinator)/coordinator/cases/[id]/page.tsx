"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import api from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiErrorMessage";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SystemFeedback } from "@/components/ui/SystemFeedback";

type CaseStatus = "open" | "in_progress" | "resolved" | "closed";
type CaseInteraction = {
  id: number;
  channel: string;
  logged_at: string;
  notes: string;
  outcome?: string | null;
};
type SupportCase = {
  id: number;
  priority: string;
  status: CaseStatus;
  interactions: CaseInteraction[];
};

const statusLabels: Record<Exclude<CaseStatus, "open">, string> = {
  in_progress: "Start work",
  resolved: "Resolve",
  closed: "Close case",
};

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<SupportCase | null>(null);
  const [channel, setChannel] = useState("note");
  const [notes, setNotes] = useState("");
  const [outcome, setOutcome] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingInteraction, setSavingInteraction] = useState(false);
  const [transition, setTransition] = useState<Exclude<CaseStatus, "open"> | null>(null);
  const [statusNote, setStatusNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData((await api.get<SupportCase>("/api/v1/cases/" + id)).data);
      setError("");
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "Unable to load this support case."));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  async function logInteraction(event: FormEvent) {
    event.preventDefault();
    if (!notes.trim()) {
      setError("Enter the notes from this interaction before saving.");
      return;
    }
    setSavingInteraction(true);
    setError("");
    try {
      await api.post("/api/v1/cases/" + id + "/interactions", {
        channel,
        notes: notes.trim(),
        outcome: outcome.trim() || null,
      });
      setNotes("");
      setOutcome("");
      await load();
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "Unable to save this case interaction."));
    } finally {
      setSavingInteraction(false);
    }
  }

  async function saveStatusChange(reason: string) {
    if (!transition) return;
    const note = transition === "closed" ? reason.trim() : statusNote.trim();
    await api.patch("/api/v1/cases/" + id + "/status", {
      status: transition,
      note: note || null,
    });
    const savedStatus = transition;
    setTransition(null);
    setStatusNote("");
    setError("");
    await load();
    const label = statusLabels[savedStatus].replace(" case", "").toLowerCase();
    setError("");
    void label;
  }

  function requestStatusChange(nextStatus: Exclude<CaseStatus, "open">) {
    setStatusNote("");
    setError("");
    setTransition(nextStatus);
  }

  if (loading && !data) return <p role="status" className="app-caption">Loading support case...</p>;
  if (!data) return <div className="max-w-3xl"><SystemFeedback tone="danger" title="Support case could not be loaded" description={error || "The case is unavailable."} /><Button className="mt-4" variant="outline" onClick={() => void load()}>Try again</Button></div>;

  const options: Exclude<CaseStatus, "open">[] = ["in_progress", "resolved", "closed"];

  return <div className="max-w-4xl">
    <h1 className="text-3xl font-bold">Case #{data.id}</h1>
    <p className="my-3 capitalize">{data.priority} priority · {data.status.replaceAll("_", " ")}</p>
    {error && <SystemFeedback className="mb-4" tone="danger" title="Case action needs attention" description={error} />}
    <div className="flex flex-wrap gap-3">
      {options.filter((status) => data.status !== status && data.status !== "closed").map((status) => <Button key={status} type="button" variant={status === "closed" ? "danger" : "outline"} onClick={() => requestStatusChange(status)}>{statusLabels[status]}</Button>)}
    </div>

    <h2 className="mb-3 mt-8 text-xl font-bold">Timeline</h2>
    <div className="space-y-3">
      {data.interactions.map((item) => <article key={item.id} className="border-l-2 border-emerald-400 py-2 pl-4">
        <p><strong className="capitalize">{item.channel}</strong> · {new Date(item.logged_at).toLocaleString()}</p>
        <p className="mt-1 whitespace-pre-wrap">{item.notes}</p>
        {item.outcome && <p className="app-caption mt-1 text-sm">Outcome: {item.outcome}</p>}
      </article>)}
      {!data.interactions.length && <p className="app-caption">No interactions have been recorded for this case.</p>}
    </div>

    <form onSubmit={logInteraction} className="mt-8 grid max-w-xl gap-3">
      <h2 className="text-lg font-semibold">Log an interaction</h2>
      <label><span className="field-label">Channel</span><select value={channel} onChange={(event) => setChannel(event.target.value)}>
        <option value="note">Note</option><option value="call">Call</option><option value="email">Email</option><option value="meeting">Meeting</option>
      </select></label>
      <label><span className="field-label">Notes</span><textarea required maxLength={10000} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="What happened?" /></label>
      <label><span className="field-label">Outcome (optional)</span><input maxLength={2000} value={outcome} onChange={(event) => setOutcome(event.target.value)} placeholder="Next step or result" /></label>
      <Button type="submit" loading={savingInteraction}>Save interaction</Button>
    </form>

    <ConfirmDialog
      open={transition !== null}
      title={transition === "closed" ? "Close this support case?" : "Update this case?"}
      description={transition === "closed"
        ? "Add a closing note so the case history explains why it was closed."
        : "This change will update the case status and be recorded in its timeline."}
      confirmLabel={transition ? statusLabels[transition] : "Confirm"}
      tone={transition === "closed" ? "danger" : "primary"}
      requireReason={transition === "closed"}
      onClose={() => { setTransition(null); setStatusNote(""); }}
      onConfirm={saveStatusChange}
    >
      {transition && transition !== "closed" && <label className="block"><span className="field-label">Status note (optional)</span><textarea rows={3} value={statusNote} onChange={(event) => setStatusNote(event.target.value)} placeholder="Add context for the case history" /></label>}
    </ConfirmDialog>
  </div>;
}