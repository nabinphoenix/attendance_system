"use client";

import { FormEvent, KeyboardEvent, ReactNode, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";

type Provider = { name: string; configured: boolean };
type AgentStatus = { enabled: boolean; providers: Provider[]; confirmation_expire_minutes: number };
type Preview = Record<string, unknown>;
type AgentResponse = {
  status: "completed" | "confirmation_required" | "error";
  message: string;
  provider?: string | null;
  fallback_attempts: string[];
  preview?: Preview | null;
  confirmation_token?: string | null;
};
type Message = { id: number; role: "user" | "assistant"; content: string; provider?: string | null; createdAt: string };
type Chat = { id: string; title: string; messages: Message[] };
type Pending = { token: string; preview: Preview };

function tableCells(line: string) {
  const value = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return value.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line: string) {
  return tableCells(line).length > 0 && tableCells(line).every((cell) => /^:?-{3,}:?$/.test(cell));
}

function inlineMarkdown(value: string, keyPrefix: string): ReactNode[] {
  const tokens = value.split(/(\*\*[^*]+\*\*|__[^_]+__|\x60[^\x60]+\x60|\*[^*]+\*|_[^_]+_|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g);
  return tokens.map((token, index) => {
    if (!token) return null;
    if ((token.startsWith("**") && token.endsWith("**")) || (token.startsWith("__") && token.endsWith("__"))) {
      return <strong key={keyPrefix + "-" + index}>{token.slice(2, -2)}</strong>;
    }
    if ((token.startsWith("*") && token.endsWith("*")) || (token.startsWith("_") && token.endsWith("_"))) {
      return <em key={keyPrefix + "-" + index}>{token.slice(1, -1)}</em>;
    }
    if (token.startsWith("\x60") && token.endsWith("\x60")) {
      return <code key={keyPrefix + "-" + index}>{token.slice(1, -1)}</code>;
    }
    const link = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
    if (link) {
      return <a key={keyPrefix + "-" + index} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a>;
    }
    return <span key={keyPrefix + "-" + index}>{token}</span>;
  }).filter(Boolean) as ReactNode[];
}

function MarkdownMessage({ content }: { content: string }) {
  const normalized = content.replace(/\\([*_|\x60])/g, "$1");
  const lines = normalized.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  let blockKey = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const heading = line.match(/^\s{0,3}(#{1,3})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      const Heading = ("h" + heading[1].length) as "h1" | "h2" | "h3";
      blocks.push(<Heading key={"block-" + blockKey++}>{inlineMarkdown(heading[2], "heading-" + blockKey)}</Heading>);
      index += 1;
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = tableCells(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="assistant-table-wrap" key={"block-" + blockKey++}>
          <table>
            <thead><tr>{headers.map((header, cellIndex) => <th key={"header-" + cellIndex}>{inlineMarkdown(header, "header-" + cellIndex)}</th>)}</tr></thead>
            <tbody>{rows.map((row, rowIndex) => <tr key={"row-" + rowIndex}>{headers.map((_, cellIndex) => <td key={"cell-" + rowIndex + "-" + cellIndex}>{inlineMarkdown(row[cellIndex] ?? "", "cell-" + rowIndex + "-" + cellIndex)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }

    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      const items: string[] = [];
      const orderedList = Boolean(ordered);
      while (index < lines.length) {
        const item = lines[index].match(orderedList ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-*]\s+(.+)$/);
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      const List = orderedList ? "ol" : "ul";
      blocks.push(<List key={"block-" + blockKey++}>{items.map((item, itemIndex) => <li key={"item-" + itemIndex}>{inlineMarkdown(item, "item-" + itemIndex)}</li>)}</List>);
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim()) {
      const nextLine = lines[index];
      const startsBlock = nextLine.match(/^\s{0,3}#{1,3}\s+/) || nextLine.match(/^\s*[-*]\s+.+$/) || nextLine.match(/^\s*\d+[.)]\s+.+$/);
      const startsTable = nextLine.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1]);
      if (paragraph.length && (startsBlock || startsTable)) break;
      paragraph.push(nextLine.trim());
      index += 1;
    }
    blocks.push(<p key={"block-" + blockKey++}>{inlineMarkdown(paragraph.join(" "), "paragraph-" + blockKey)}</p>);
  }

  return <div className="assistant-markdown">{blocks}</div>;
}
const examples = [
  "List the current intakes and their cohort semesters.",
  "Create a program called Bachelor of Computer Applications.",
  "Show attendance for section 1.",
  "Show the students at risk because of attendance.",
];

export default function AssistantPage() {
  const welcome = useMemo<Message>(() => ({ id: 1, role: "assistant", content: "I can look up academic and attendance data, then prepare safe, auditable proposals for you to review. I never apply a change until you confirm it.", createdAt: new Date().toISOString() }), []);
  const [chats, setChats] = useState<Chat[]>([]);
  const [chatId, setChatId] = useState("");
  const [messages, setMessages] = useState<Message[]>([welcome]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const saved = window.localStorage.getItem("antimbench-assistant-chats");
    if (saved) { try { const parsed = JSON.parse(saved) as Chat[]; if (parsed.length) { setChats(parsed); setChatId(parsed[0].id); setMessages(parsed[0].messages); return; } } catch { /* ignore corrupt local history */ } }
    const initial = { id: crypto.randomUUID(), title: "New chat", messages: [welcome] };
    setChats([initial]); setChatId(initial.id);
  }, []);

  useEffect(() => {
    if (!chatId) return;
    setChats((items) => { const updated = items.map((chat) => chat.id === chatId ? { ...chat, messages } : chat); window.localStorage.setItem("antimbench-assistant-chats", JSON.stringify(updated)); return updated; });
  }, [chatId, messages]);

  useEffect(() => { if (chats.length) window.localStorage.setItem("antimbench-assistant-chats", JSON.stringify(chats)); }, [chats]);

  function newChat() { const fresh = { id: crypto.randomUUID(), title: "New chat", messages: [welcome] }; setChats((items) => [fresh, ...items]); setChatId(fresh.id); setMessages(fresh.messages); setPending(null); setInput(""); }
  function selectChat(id: string) { const chat = chats.find((item) => item.id === id); if (!chat) return; setChatId(id); setMessages(chat.messages); setPending(null); setInput(""); }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fileId = params.get("googleFileId");
    if (!fileId) return;
    const title = params.get("googleFileTitle") || "selected file";
    const type = params.get("googleFileType") || "Form or Sheet";
    setInput(`Analyze this Google ${type} for teacher feedback: "${title}" (Google file ID: ${fileId}). Read only this file. Report the sample size, rating patterns, repeated strengths, improvement themes, and constructive recommendations. Do not identify respondents.`);
  }, []);

  useEffect(() => {
    api.get<AgentStatus>("/api/v1/agent/status").then((response) => setStatus(response.data)).catch(() => setError("Unable to check the assistant configuration."));
  }, []);

  async function send(event?: FormEvent, preset?: string) {
    event?.preventDefault();
    const message = (preset ?? input).trim();
    if (!message || loading || pending) return;
    setError("");
    setInput("");
    setLoading(true);
    setMessages((items) => [...items, { id: Date.now(), role: "user", content: message, createdAt: new Date().toISOString() }]);
    try {
      const response = await api.post<AgentResponse>("/api/v1/agent/chat", { message });
      const data = response.data;
      setMessages((items) => [...items, { id: Date.now() + 1, role: "assistant", content: data.message, provider: data.provider, createdAt: new Date().toISOString() }]);
      if (data.confirmation_token && data.preview) setPending({ token: data.confirmation_token, preview: data.preview });
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "The assistant could not complete that request.");
    } finally {
      setLoading(false);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    void send();
  }

  async function confirm() {
    if (!pending) return;
    setConfirming(true);
    setError("");
    try {
      const response = await api.post("/api/v1/agent/confirm", { confirmation_token: pending.token });
      setMessages((items) => [...items, { id: Date.now(), role: "assistant", content: response.data.message, createdAt: new Date().toISOString() }]);
      setPending(null);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "The proposed action could not be applied.");
    } finally {
      setConfirming(false);
    }
  }

  async function cancel() {
    if (!pending) return;
    setConfirming(true);
    try {
      await api.post("/api/v1/agent/cancel", { confirmation_token: pending.token });
      setMessages((items) => [...items, { id: Date.now(), role: "assistant", content: "The proposal was cancelled. No data was changed.", createdAt: new Date().toISOString() }]);
      setPending(null);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail ?? "The proposal could not be cancelled.");
    } finally {
      setConfirming(false);
    }
  }

  const configured = status?.providers.filter((provider) => provider.configured).map((provider) => provider.name) ?? [];
  const summary = typeof pending?.preview.summary === "string" ? pending.preview.summary : "Review the proposed action before applying it.";
  const errors = Array.isArray(pending?.preview.errors) ? pending.preview.errors.filter((item): item is string => typeof item === "string") : [];

  return <div className="mx-auto max-w-6xl">
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl font-bold">AI assistant</h1>
        <p className="mt-2 max-w-3xl text-slate-400">Ask in plain language. The assistant can read approved data and prepare guarded academic changes. Every change requires your separate confirmation.</p>
      </div>
      <div className={`rounded-lg border px-3 py-2 text-xs ${configured.length ? "border-emerald-500/40 text-emerald-300" : "border-amber-500/40 text-amber-200"}`}>
        {configured.length ? "Configured providers: " + configured.join(" -> ") : "No AI provider configured"}
      </div>
    </div>

    <section className="grid gap-4 md:grid-cols-[12rem_1fr] rounded-xl border border-slate-800 bg-slate-900 p-4 shadow-sm">
      <aside className="border-b border-slate-800 pb-3 md:border-b-0 md:border-r md:pr-3"><Button type="button" onClick={newChat} className="w-full">New chat</Button><div className="mt-3 space-y-1">{chats.map((chat) => <button key={chat.id} type="button" onClick={() => selectChat(chat.id)} className={`w-full truncate rounded px-2 py-2 text-left text-xs ${chat.id === chatId ? "bg-emerald-500/20 text-emerald-200" : "text-slate-400 hover:bg-slate-800"}`}>{chat.title}</button>)}</div></aside>
      <div>
      <div className="max-h-[28rem] min-h-72 space-y-4 overflow-y-auto pr-1">
        {messages.map((message) => <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
          <div className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-6 ${message.role === "user" ? "bg-emerald-500 text-slate-950" : "border border-slate-700 bg-slate-950 text-slate-200"}`}>
            {message.role === "assistant" ? <MarkdownMessage content={message.content} /> : <p className="whitespace-pre-wrap">{message.content}</p>}
            <p className="mt-2 text-xs opacity-60">{message.createdAt ? new Date(message.createdAt).toLocaleString() : ""}</p>{message.provider && <p className="text-xs opacity-60">Answered by {message.provider}</p>}
          </div>
        </div>)}
        {loading && <div className="flex justify-start"><div className="rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-400">Working safely?</div></div>}
      </div>

      {pending && <div className="mt-4 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
        <p className="font-semibold text-amber-100">Confirmation required</p>
        <p className="mt-1 text-sm text-amber-50/90">{summary}</p>
        {typeof pending.preview.promote_count === "number" && <p className="mt-2 text-sm text-amber-100">{String(pending.preview.promote_count)} promote - {String(pending.preview.hold_count ?? 0)} hold - {String(pending.preview.total_students ?? 0)} total students</p>}
        {errors.map((item) => <p key={item} className="mt-2 text-sm text-red-300">{item}</p>)}
        <details className="mt-3 text-sm text-amber-50/90"><summary className="cursor-pointer font-medium">View exact proposal data</summary><pre className="mt-2 max-h-52 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-300">{JSON.stringify(pending.preview, null, 2)}</pre></details>
        <div className="mt-4 flex flex-wrap gap-3"><Button onClick={() => void confirm()} loading={confirming} disabled={Boolean(errors.length)}>Confirm and apply</Button><Button variant="outline" onClick={() => void cancel()} disabled={confirming}>Cancel</Button></div>
      </div>}

      {error && <p className="mt-4 text-sm text-red-400" role="alert">{error}</p>}
      <form className="mt-4 flex gap-3" onSubmit={(event) => void send(event)}>
        <label className="sr-only" htmlFor="assistant-message">Ask the assistant</label>
        <textarea id="assistant-message" value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={handleComposerKeyDown} disabled={loading || Boolean(pending)} rows={3} maxLength={4000} placeholder={pending ? "Confirm or cancel the current proposal before starting another request." : "Press Enter to send; Shift+Enter for a new line."} className="min-h-20 flex-1 resize-y rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none transition focus:border-emerald-400 disabled:cursor-not-allowed disabled:opacity-60" />
        <Button type="submit" loading={loading} disabled={!input.trim() || Boolean(pending)} className="self-end">Send</Button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">{examples.map((example) => <button key={example} type="button" onClick={() => void send(undefined, example)} disabled={loading || Boolean(pending)} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-50">{example}</button>)}</div>
      </div>
    </section>

    <p className="mt-4 text-xs text-slate-500">Your request and the minimum tool result needed to answer it are sent to the selected cloud provider. Provider API keys remain on the server. Confirmations expire after {status?.confirmation_expire_minutes ?? 10} minutes and are recorded in the audit log.</p>
  </div>;
}
