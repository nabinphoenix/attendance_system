"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { SystemFeedback } from "@/components/ui/SystemFeedback";

type Network = { id: number; label: string; cidr: string; is_active: boolean; created_at: string };
type Policy = "off" | "flag";

export default function Page() {
  const [networks, setNetworks] = useState<Network[]>([]);
  const [policy, setPolicy] = useState<Policy>("flag");
  const [label, setLabel] = useState("");
  const [cidr, setCidr] = useState("");
  const [detectedIp, setDetectedIp] = useState<string | null>(null);
  const [detectedLabel, setDetectedLabel] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editCidr, setEditCidr] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [list, settings] = await Promise.all([
        api.get<Network[]>("/api/v1/campus-networks"),
        api.get<{ ip_policy: Policy }>("/api/v1/campus-networks/policy"),
      ]);
      setNetworks(list.data);
      setPolicy(settings.data.ip_policy);
      setError("");
    } catch (requestError: any) {
      setError(String(requestError.response?.data?.detail ?? "Unable to load campus networks."));
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function saveNetwork(event: FormEvent) {
    event.preventDefault();
    if (!label.trim() || !cidr.trim()) return;
    const broad = isBroadRange(cidr);
    if (broad && !window.confirm("This range is wider than IPv4 /16 or IPv6 /48. Register it anyway?")) return;
    setBusy(true);
    setError("");
    try {
      await api.post("/api/v1/campus-networks", { label: label.trim(), cidr: cidr.trim(), force: broad });
      setLabel("");
      setCidr("");
      setMessage("Campus network added.");
      await load();
    } catch (requestError: any) {
      setError(String(requestError.response?.data?.detail ?? "Unable to add network."));
    } finally { setBusy(false); }
  }

  async function detectNetwork() {
    setBusy(true);
    setError("");
    setDetectedIp(null);
    try {
      const { data } = await api.get<{ detected_ip: string | null }>("/api/v1/campus-networks/current");
      if (!data.detected_ip) throw new Error("Your public IP could not be determined.");
      setDetectedIp(data.detected_ip);
      setDetectedLabel("My current campus network");
    } catch (requestError: any) {
      setError(String(requestError.response?.data?.detail ?? requestError.message ?? "Unable to detect your network."));
    } finally { setBusy(false); }
  }

  async function confirmDetectedNetwork() {
    if (!detectedIp || !detectedLabel.trim()) return;
    setBusy(true);
    setError("");
    try {
      // The backend resolves the request IP again; the detected value is never submitted.
      await api.post("/api/v1/campus-networks/current/confirm", { label: detectedLabel.trim() });
      setDetectedIp(null);
      setMessage("Current network added after confirmation.");
      await load();
    } catch (requestError: any) {
      setError(String(requestError.response?.data?.detail ?? "Unable to save your current network."));
    } finally { setBusy(false); }
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (editing === null || !editLabel.trim() || !editCidr.trim()) return;
    const broad = isBroadRange(editCidr);
    if (broad && !window.confirm("This range is wider than IPv4 /16 or IPv6 /48. Save it anyway?")) return;
    setBusy(true);
    setError("");
    try {
      await api.patch(`/api/v1/campus-networks/${editing}`, { label: editLabel.trim(), cidr: editCidr.trim(), force: broad });
      setEditing(null);
      setMessage("Campus network updated.");
      await load();
    } catch (requestError: any) {
      setError(String(requestError.response?.data?.detail ?? "Unable to update network."));
    } finally { setBusy(false); }
  }

  async function deactivate(id: number) {
    if (!window.confirm("Deactivate this campus network? Existing attendance records remain unchanged.")) return;
    setBusy(true);
    setError("");
    try {
      await api.post(`/api/v1/campus-networks/${id}/deactivate`);
      setMessage("Campus network deactivated.");
      await load();
    } catch (requestError: any) {
      setError(String(requestError.response?.data?.detail ?? "Unable to deactivate network."));
    } finally { setBusy(false); }
  }

  async function changePolicy(value: Policy) {
    setBusy(true);
    setError("");
    try {
      await api.patch("/api/v1/campus-networks/policy", { ip_policy: value });
      setPolicy(value);
      setMessage("Network policy updated. IP evidence never blocks or overrides location checks.");
    } catch (requestError: any) {
      setError(String(requestError.response?.data?.detail ?? "Unable to update network policy."));
    } finally { setBusy(false); }
  }

  return <div className="max-w-5xl space-y-6">
    <PageHeader title="Campus networks" description="Register your college's public IP ranges. Network evidence is informational and never changes a GPS-based attendance decision." />
    {error && <SystemFeedback tone="danger" title="Network settings error" description={error} />}
    {message && <SystemFeedback tone="success" title="Saved" description={message} />}
    <section className="panel p-5 sm:p-6">
      <h2 className="text-lg font-semibold">Network policy</h2>
      <p className="mt-1 text-sm text-slate-400">Flag records and displays network status. Off stores the detected IP but reports status as unknown.</p>
      <select className="mt-4 w-full sm:max-w-xs" aria-label="Network policy" value={policy} disabled={busy} onChange={(event) => void changePolicy(event.target.value as Policy)}>
        <option value="flag">Flag (informational)</option>
        <option value="off">Off</option>
      </select>
    </section>
    <section className="panel p-5 sm:p-6">
      <h2 className="text-lg font-semibold">Add a campus network</h2>
      <p className="mt-1 text-sm text-slate-400">Use a public IP in CIDR notation, for example 124.41.240.125/32. Do not enter a private router address.</p>
      <form className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end" onSubmit={(event) => void saveNetwork(event)}>
        <label><span className="field-label">Label</span><input className="w-full" maxLength={120} required value={label} onChange={(event) => setLabel(event.target.value)} /></label>
        <label><span className="field-label">Public IP / CIDR</span><input className="w-full" maxLength={64} required value={cidr} onChange={(event) => setCidr(event.target.value)} placeholder="124.41.240.125/32" /></label>
        <Button type="submit" disabled={busy}>Add network</Button>
      </form>
      <div className="mt-6 border-t border-slate-700 pt-5">
        <Button type="button" variant="outline" disabled={busy} onClick={() => void detectNetwork()}>Add My Current Network</Button>
        {detectedIp && <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
          <p className="text-sm">Detected public IP: <span className="font-mono font-semibold">{detectedIp}</span> — this has not been saved.</p>
          <label className="mt-3 block"><span className="field-label">Network label</span><input className="w-full sm:max-w-sm" value={detectedLabel} maxLength={120} onChange={(event) => setDetectedLabel(event.target.value)} /></label>
          <div className="mt-3 flex flex-wrap gap-2"><Button type="button" disabled={busy || !detectedLabel.trim()} onClick={() => void confirmDetectedNetwork()}>Confirm and save</Button><Button type="button" variant="ghost" onClick={() => setDetectedIp(null)}>Cancel</Button></div>
        </div>}
      </div>
    </section>
    <section className="panel p-5 sm:p-6">
      <h2 className="text-lg font-semibold">Registered networks</h2>
      <div className="mt-4 space-y-3">
        {networks.map((network) => <div key={network.id} className="rounded-lg border border-slate-700 p-4">
          {editing === network.id ? <form className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => void saveEdit(event)}>
            <input aria-label="Edit label" maxLength={120} required value={editLabel} onChange={(event) => setEditLabel(event.target.value)} />
            <input aria-label="Edit CIDR" maxLength={64} required value={editCidr} onChange={(event) => setEditCidr(event.target.value)} />
            <div className="flex gap-2"><Button type="submit" disabled={busy}>Save</Button><Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button></div>
          </form> : <div className="flex flex-wrap items-center justify-between gap-3">
            <div><p className="font-semibold">{network.label} <span className={network.is_active ? "text-emerald-400" : "text-slate-400"}>· {network.is_active ? "Active" : "Inactive"}</span></p><p className="mt-1 font-mono text-sm text-slate-300">{network.cidr}</p></div>
            <div className="flex gap-2"><Button type="button" variant="outline" disabled={busy} onClick={() => { setEditing(network.id); setEditLabel(network.label); setEditCidr(network.cidr); }}>Edit</Button>{network.is_active && <Button type="button" variant="ghost" disabled={busy} onClick={() => void deactivate(network.id)}>Deactivate</Button>}</div>
          </div>}
        </div>)}
        {!networks.length && <p className="text-sm text-slate-400">No campus networks have been registered yet.</p>}
      </div>
    </section>
  </div>;
}

function isBroadRange(cidr: string): boolean {
  const parts = cidr.trim().split("/");
  if (parts.length !== 2) return false;
  const prefix = Number(parts[1]);
  return Number.isInteger(prefix) && prefix < (parts[0].includes(":") ? 48 : 16);
}
