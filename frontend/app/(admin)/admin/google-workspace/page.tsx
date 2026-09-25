"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { apiErrorMessage } from "@/lib/apiErrorMessage";
import { notifySystemFeedback } from "@/lib/systemFeedback";

type Status = {
  configured: boolean;
  connected: boolean;
  google_email?: string | null;
  connected_at?: string | null;
  allowed_workspace_domain?: string | null;
  drive_listing_ready?: boolean;
};

type Confirmation = { kind: "disconnect" } | { kind: "delete"; resource: Resource };

type Resource = {
  id: number;
  resource_type: "form" | "spreadsheet" | "folder";
  title: string;
  url: string;
  created_at: string;
};

type SheetPreview = { range?: string | null; values: unknown[][] };

type DriveFile = {
  id: string;
  name: string;
  mime_type: string;
  url?: string | null;
  modified_time?: string | null;
  icon_url?: string | null;
  managed_resource_id?: number | null;
};

type FormItem = {
  title?: string;
  description?: string;
  questionItem?: { question?: {
    required?: boolean;
    choiceQuestion?: { type?: string; options?: { value?: string }[] };
    scaleQuestion?: { low?: number; high?: number; lowLabel?: string; highLabel?: string };
    textQuestion?: { paragraph?: boolean };
  } };
};

type GoogleForm = { form_id: string; title: string; description?: string | null; responder_uri?: string | null; items: FormItem[] };
type FormAnswer = { textAnswers?: { answers?: { value?: string }[] }; fileUploadAnswers?: { answers?: { fileName?: string }[] } };
type FormResponse = { lastSubmittedTime?: string; createTime?: string; answers?: Record<string, FormAnswer> };
type FormResponsePage = { responses: FormResponse[]; question_titles: Record<string, string>; next_page_token?: string | null };
type GoogleSheet = { spreadsheet_id: string; title: string; sheets: { title: string; index?: number; sheetId: number }[] };

function requestError(error: unknown) {
  return apiErrorMessage(error, "Google Workspace could not complete this request. Check the account connection, permissions, and server setup, then try again.");
}

function typeLabel(type: Resource["resource_type"]) {
  return type === "form" ? "Google Form" : type === "spreadsheet" ? "Google Sheet" : "Drive folder";
}

function googleFormItemSummary(item: FormItem) {
  const question = item.questionItem?.question;
  if (!question) return item.description || "Section";
  if (question.choiceQuestion) {
    const kind = question.choiceQuestion.type === "CHECKBOX" ? "Select all that apply" : "Choose one";
    const options = question.choiceQuestion.options?.map((option) => option.value).filter(Boolean).join(", ");
    return options ? `${kind}: ${options}` : kind;
  }
  if (question.scaleQuestion) {
    const scale = question.scaleQuestion;
    return `Rating scale ${scale.low ?? 1}–${scale.high ?? 5}${scale.lowLabel || scale.highLabel ? ` (${scale.lowLabel || "low"} to ${scale.highLabel || "high"})` : ""}`;
  }
  if (question.textQuestion) return question.textQuestion.paragraph ? "Long answer" : "Short answer";
  return "Question";
}

function respondentEmbedUrl(uri?: string | null) {
  if (!uri) return "";
  try {
    const url = new URL(uri);
    if (url.hostname !== "docs.google.com") return "";
    url.searchParams.set("embedded", "true");
    return url.toString();
  } catch { return ""; }
}


function responseAnswerValues(answer: FormAnswer) {
  const textValues = answer.textAnswers?.answers?.map((item) => item.value).filter((value): value is string => Boolean(value)) ?? [];
  if (textValues.length) return textValues;
  const fileValues = answer.fileUploadAnswers?.answers?.map((item) => item.fileName).filter((value): value is string => Boolean(value)) ?? [];
  return fileValues.length ? fileValues.map((name) => `File uploaded: ${name}`) : ["No text answer"];
}

function driveFileTypeLabel(file: DriveFile) {
  if (file.mime_type === "application/vnd.google-apps.form") return "Google Form";
  if (file.mime_type === "application/vnd.google-apps.spreadsheet") return "Google Sheet";
  if (file.mime_type === "application/vnd.google-apps.folder") return "Drive folder";
  return "Drive file";
}

export default function GoogleWorkspacePage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status | null>(null);
  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [driveFiles, setDriveFiles] = useState<DriveFile[]>([]);
  const [driveQuery, setDriveQuery] = useState("");
  const [driveType, setDriveType] = useState("all");
  const [driveNextPage, setDriveNextPage] = useState<string | null>(null);
  const [driveLoading, setDriveLoading] = useState(false);
  const [activeFileId, setActiveFileId] = useState<string | null>(null);
  const [formPreviews, setFormPreviews] = useState<Record<string, GoogleForm>>({});
  const [driveFormResponses, setDriveFormResponses] = useState<Record<string, FormResponsePage>>({});
  const [googleSheets, setGoogleSheets] = useState<Record<string, GoogleSheet>>({});
  const [googleSheetValues, setGoogleSheetValues] = useState<Record<string, SheetPreview>>({});
  const [googleSheetTabs, setGoogleSheetTabs] = useState<Record<string, string>>({});
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [sheetTitle, setSheetTitle] = useState("");
  const [folderTitle, setFolderTitle] = useState("");
  const [draftTitles, setDraftTitles] = useState<Record<number, string>>({});
  const [formResponses, setFormResponses] = useState<Record<number, unknown[]>>({});
  const [sheetRange, setSheetRange] = useState<Record<number, string>>({});
  const [sheetValues, setSheetValues] = useState<Record<number, string>>({});
  const [sheetPreview, setSheetPreview] = useState<Record<number, SheetPreview>>({});

  const callbackResult = useMemo(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("google") || "";
  }, []);
  const callbackReason = useMemo(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("google_reason") || "";
  }, []);

  async function loadDriveFiles(query = driveQuery, fileType = driveType, pageToken?: string, append = false) {
    setDriveLoading(true); setError("");
    try {
      const response = await api.get<{ files: DriveFile[]; next_page_token?: string | null }>("/api/v1/google-workspace/drive/files", {
        params: { query: query.trim() || undefined, type: fileType, page_size: 50, page_token: pageToken },
      });
      setDriveFiles((current) => append ? [...current, ...response.data.files] : response.data.files);
      setDriveNextPage(response.data.next_page_token || null);
    } catch (fetchError) { setError(requestError(fetchError)); }
    finally { setDriveLoading(false); }
  }
  const refresh = useCallback(async () => {
    const statusResponse = await api.get<Status>("/api/v1/google-workspace/status");
    setStatus(statusResponse.data);
    const resourcesResponse = await api.get<Resource[]>("/api/v1/google-workspace/resources");
    setResources(resourcesResponse.data);
    if (statusResponse.data.connected && statusResponse.data.drive_listing_ready) {
      setDriveLoading(true);
      try {
        const response = await api.get<{ files: DriveFile[]; next_page_token?: string | null }>("/api/v1/google-workspace/drive/files", {
          params: { type: "all", page_size: 50 },
        });
        setDriveFiles(response.data.files);
        setDriveNextPage(response.data.next_page_token || null);
      } catch (fetchError) {
        setError(requestError(fetchError));
      } finally {
        setDriveLoading(false);
      }
    } else {
      setDriveFiles([]);
      setDriveNextPage(null);
    }
    return statusResponse.data;
  }, []);
  async function previewDriveFile(file: DriveFile) {
    setActiveFileId(file.id); setError("");
    if (file.mime_type === "application/vnd.google-apps.form") {
      if (formPreviews[file.id]) return;
      setBusy(`preview-${file.id}`);
      try {
        const response = await api.get<GoogleForm>(`/api/v1/google-workspace/drive/files/${encodeURIComponent(file.id)}/form`);
        setFormPreviews((current) => ({ ...current, [file.id]: response.data }));
      } catch (previewError) { setError(requestError(previewError)); }
      finally { setBusy(""); }
      return;
    }
    if (file.mime_type === "application/vnd.google-apps.spreadsheet") {
      setBusy(`preview-${file.id}`);
      try {
        const sheet = googleSheets[file.id] ?? (await api.get<GoogleSheet>(`/api/v1/google-workspace/drive/files/${encodeURIComponent(file.id)}/spreadsheet`)).data;
        setGoogleSheets((current) => ({ ...current, [file.id]: sheet }));
        const tab = googleSheetTabs[file.id] || sheet.sheets[0]?.title || "Sheet1";
        setGoogleSheetTabs((current) => ({ ...current, [file.id]: tab }));
        if (!googleSheetValues[file.id]) await readDriveSheetValues(file.id, tab);
      } catch (previewError) { setError(requestError(previewError)); }
      finally { setBusy(""); }
    }
  }

  async function readDriveSheetValues(fileId: string, tabTitle: string) {
    const range = `'${tabTitle.replace(/'/g, "''")}'!A1:Z100`;
    setBusy(`sheet-${fileId}`); setError("");
    try {
      const response = await api.get<SheetPreview>(`/api/v1/google-workspace/drive/files/${encodeURIComponent(fileId)}/values`, { params: { range } });
      setGoogleSheetValues((current) => ({ ...current, [fileId]: response.data }));
    } catch (readError) { setError(requestError(readError)); }
    finally { setBusy(""); }
  }

  async function readDriveResponses(fileId: string, pageToken?: string, append = false) {
    setActiveFileId(fileId); setBusy(`responses-${fileId}`); setError("");
    try {
      const response = await api.get<FormResponsePage>(`/api/v1/google-workspace/drive/files/${encodeURIComponent(fileId)}/responses`, { params: { page_size: 50, page_token: pageToken } });
      setDriveFormResponses((current) => ({ ...current, [fileId]: append && current[fileId] ? { ...response.data, responses: [...current[fileId].responses, ...response.data.responses] } : response.data }));
    } catch (readError) { setError(requestError(readError)); }
    finally { setBusy(""); }
  }

  function analyzeInAssistant(file: DriveFile) {
    const fileType = file.mime_type === "application/vnd.google-apps.form" ? "Form" : "Sheet";
    const params = new URLSearchParams({ googleFileId: file.id, googleFileTitle: file.name, googleFileType: fileType });
    router.push(`/admin/assistant?${params.toString()}`);
  }

  useEffect(() => {
    let active = true;
    void refresh().then((workspaceStatus) => {
      if (!active) return;
      if (!workspaceStatus.configured) {
        notifySystemFeedback({
          tone: "warning",
          title: "Google Workspace setup is incomplete",
          description: "Configure the Google OAuth client ID, secret, redirect URL, and allowed Workspace domain on the server, then restart the API.",
        });
      } else if (!workspaceStatus.connected && !callbackResult) {
        notifySystemFeedback({
          tone: "warning",
          title: "Google account is not connected",
          description: "Connect the college admin account" + (workspaceStatus.allowed_workspace_domain ? " (@" + workspaceStatus.allowed_workspace_domain + ")" : "") + " to browse and read its Forms and Sheets here.",
        });
      } else if (!workspaceStatus.drive_listing_ready) {
        notifySystemFeedback({
          tone: "warning",
          title: "Google Drive access needs updating",
          description: "Reconnect and approve the Drive listing permission to find existing Forms and Sheets in this account.",
        });
      }
    }).catch((fetchError) => {
      if (active) setError(requestError(fetchError));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [callbackResult, refresh]);

  useEffect(() => {
    if (callbackResult === "connected") {
      setNotice("Google Workspace connected successfully.");
      notifySystemFeedback({ tone: "success", title: "Google Workspace connected", description: "The college Google account is ready to use." });
    }
    if (callbackResult === "cancelled") {
      setNotice("Google authorization was cancelled.");
      notifySystemFeedback({ tone: "info", title: "Google connection cancelled", description: "No Google account changes were made. You can connect it whenever you are ready." });
    }
    if (callbackResult === "failed") {
      const message = callbackReason || "Google authorization did not finish. Check the OAuth settings, redirect URL, approved account domain, and requested permissions, then try again.";
      setError(message);
      notifySystemFeedback({ tone: "danger", title: "Google authorization failed", description: message });
    }
  }, [callbackReason, callbackResult]);

  async function connect() {
    setBusy("connect"); setError(""); setNotice("");
    try {
      const response = await api.get<{ authorization_url: string }>("/api/v1/google-workspace/authorize");
      window.location.assign(response.data.authorization_url);
    } catch (connectError) {
      setError(requestError(connectError)); setBusy("");
    }
  }

  function disconnect() {
    setConfirmation({ kind: "disconnect" });
  }

  async function performDisconnect() {
    setBusy("disconnect"); setError(""); setNotice("");
    try {
      await api.delete("/api/v1/google-workspace/connection");
      await refresh();
      setNotice("Google Workspace was disconnected. Existing Google files were kept.");
    } catch (disconnectError) { setError(requestError(disconnectError)); }
    finally { setBusy(""); }
  }
  async function create(path: string, payload: object, success: string) {
    setBusy(path); setError(""); setNotice("");
    try {
      await api.post(path, payload);
      await refresh();
      setNotice(success);
      if (path.endsWith("/forms")) { setFormTitle(""); setFormDescription(""); }
      if (path.endsWith("/spreadsheets")) setSheetTitle("");
      if (path.endsWith("/folders")) setFolderTitle("");
    } catch (createError) { setError(requestError(createError)); }
    finally { setBusy(""); }
  }

  async function rename(resource: Resource) {
    const title = (draftTitles[resource.id] ?? resource.title).trim();
    if (!title || title === resource.title) return;
    setBusy(`rename-${resource.id}`); setError(""); setNotice("");
    try {
      await api.patch(`/api/v1/google-workspace/resources/${resource.id}`, { title });
      await refresh(); setNotice("Resource name updated.");
    } catch (renameError) { setError(requestError(renameError)); }
    finally { setBusy(""); }
  }

  function remove(resource: Resource) {
    setConfirmation({ kind: "delete", resource });
  }

  async function performRemove(resource: Resource) {
    setBusy("delete-" + resource.id); setError(""); setNotice("");
    try {
      await api.delete("/api/v1/google-workspace/resources/" + resource.id);
      await refresh(); setNotice("Resource deleted from Google Workspace.");
    } catch (deleteError) { setError(requestError(deleteError)); }
    finally { setBusy(""); }
  }

  async function confirmDestructiveAction() {
    if (!confirmation) return;
    if (confirmation.kind === "disconnect") return performDisconnect();
    return performRemove(confirmation.resource);
  }
  async function readResponses(resource: Resource) {
    setBusy(`responses-${resource.id}`); setError("");
    try {
      const response = await api.get<{ responses: unknown[] }>(`/api/v1/google-workspace/forms/${resource.id}/responses`);
      setFormResponses((current) => ({ ...current, [resource.id]: response.data.responses }));
    } catch (readError) { setError(requestError(readError)); }
    finally { setBusy(""); }
  }

  function rangeFor(resource: Resource) { return sheetRange[resource.id] || "Sheet1!A1:Z100"; }

  async function readSheet(resource: Resource) {
    setBusy(`read-sheet-${resource.id}`); setError("");
    try {
      const response = await api.get<SheetPreview>(`/api/v1/google-workspace/spreadsheets/${resource.id}/values`, { params: { range: rangeFor(resource) } });
      setSheetPreview((current) => ({ ...current, [resource.id]: response.data }));
      setSheetValues((current) => ({ ...current, [resource.id]: JSON.stringify(response.data.values, null, 2) }));
    } catch (readError) { setError(requestError(readError)); }
    finally { setBusy(""); }
  }

  async function writeSheet(resource: Resource) {
    let values: unknown[][];
    try {
      const parsed = JSON.parse(sheetValues[resource.id] || "[]");
      if (!Array.isArray(parsed) || !parsed.every(Array.isArray)) throw new Error();
      values = parsed as unknown[][];
    } catch {
      setError("Sheet values must be a JSON array of rows, for example [[\"Name\", \"Value\"], [\"A\", 1]].");
      return;
    }
    if (!values.length) { setError("Enter at least one row before updating the sheet."); return; }
    setBusy(`write-sheet-${resource.id}`); setError(""); setNotice("");
    try {
      await api.put(`/api/v1/google-workspace/spreadsheets/${resource.id}/values`, { range: rangeFor(resource), values });
      await readSheet(resource); setNotice("Sheet values updated.");
    } catch (writeError) { setError(requestError(writeError)); }
    finally { setBusy(""); }
  }

  if (loading) return <p className="app-caption" role="status">Loading Google Workspace…</p>;

  const connected = Boolean(status?.configured && status.connected);
  return <div className="min-w-0 max-w-full">
    <PageHeader title="Google Workspace" description="Create and manage this college’s Forms, Sheets, and app-managed Drive folders from one admin-only connection." />

    {notice && <p role="status" className="system-feedback system-feedback-success mb-4 rounded-xl border px-4 py-3 text-sm">{notice}</p>}
    {error && <p role="alert" className="system-feedback system-feedback-danger mb-4 rounded-xl border px-4 py-3 text-sm">{error}</p>}

    <section className="panel mb-6 flex min-w-0 flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-center lg:justify-between">
      <div className="min-w-0">
        <p className="text-sm font-semibold">Connection</p>

        {!status && <p className="helper-text">Google Workspace status could not be loaded. Use the reason shown above, then reload this page.</p>}
        {status && !status.configured && <p className="helper-text">The server still needs the Google OAuth settings. Check the backend environment and restart the API.</p>}
        {status?.configured && !status.connected && <p className="helper-text">No account is connected yet. Use the college admin’s @{status.allowed_workspace_domain} account.</p>}
        {connected && <p className="helper-text">Connected as <span className="font-semibold">{status?.google_email}</span>. Only this college’s admins can use this connection.</p>}
        {connected && !status?.drive_listing_ready && <p className="helper-text">Reconnect once to grant read-only Drive listing access, so AntimBench can find the Forms and Sheets already in this account.</p>}
      </div>
      <div className="flex flex-wrap gap-2">
        {!connected && <Button type="button" loading={busy === "connect"} disabled={!status?.configured} onClick={() => void connect()}>Connect Google Workspace</Button>}
        {connected && !status?.drive_listing_ready && <Button type="button" loading={busy === "connect"} onClick={() => void connect()}>Update Google permissions</Button>}
        {connected && <Button type="button" variant="danger" loading={busy === "disconnect"} onClick={() => void disconnect()}>Disconnect</Button>}
      </div>
    </section>
      {connected && <section aria-labelledby="drive-heading" className="panel mb-6 min-w-0 p-4 sm:p-5">
        <div className="mb-4">
          <h2 id="drive-heading" className="text-lg font-semibold">Existing Google Drive files</h2>
          <p className="helper-text mt-2">AI analysis sends only bounded, redacted data from the selected file to the configured provider after you submit on the assistant page.</p>
          <p className="helper-text mt-1">Browse files the connected Google account can access. Forms and Sheets open here in a private preview; full editing stays on Google.</p>
        </div>
        <form className="mb-4 grid min-w-0 gap-3 sm:grid-cols-[minmax(0,1fr)_12rem_auto]" onSubmit={(event) => { event.preventDefault(); void loadDriveFiles(driveQuery, driveType); }}>
          <div className="min-w-0"><label className="field-label" htmlFor="drive-search">Search Drive</label><input id="drive-search" value={driveQuery} maxLength={120} onChange={(event) => setDriveQuery(event.target.value)} placeholder="Search by file name" /></div>
          <div><label className="field-label" htmlFor="drive-file-type">File type</label><select id="drive-file-type" value={driveType} onChange={(event) => setDriveType(event.target.value)}><option value="all">All files</option><option value="form">Google Forms</option><option value="spreadsheet">Google Sheets</option><option value="folder">Folders</option><option value="other">Other files</option></select></div>
          <Button type="submit" className="self-end" loading={driveLoading}>Search</Button>
        </form>
        {!driveFiles.length && !driveLoading && <p className="app-caption rounded-lg border border-dashed p-4 text-sm">No matching files were found in the connected account.</p>}
        <div className="grid min-w-0 gap-3">
          {driveFiles.map((file) => {
            const isForm = file.mime_type === "application/vnd.google-apps.form";
            const isSheet = file.mime_type === "application/vnd.google-apps.spreadsheet";
            const isPreviewable = isForm || isSheet;
            const expanded = activeFileId === file.id;
            const form = formPreviews[file.id];
            const responsePage = driveFormResponses[file.id];
            const sheet = googleSheets[file.id];
            const sheetData = googleSheetValues[file.id];
            const embedUrl = form ? respondentEmbedUrl(form.responder_uri) : "";
            return <article key={file.id} className="min-w-0 rounded-xl border p-4">
              <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-wide text-emerald-600">{driveFileTypeLabel(file)}</p><p className="mt-1 break-words font-semibold">{file.name}</p><p className="app-caption mt-1 text-xs">{file.modified_time ? `Updated ${new Date(file.modified_time).toLocaleString()}` : "Google Drive file"}</p></div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  {isPreviewable && <Button type="button" variant="outline" size="sm" loading={busy === `preview-${file.id}`} onClick={() => expanded ? setActiveFileId(null) : void previewDriveFile(file)}>{expanded ? "Close preview" : "Preview"}</Button>}
                  {isPreviewable && <Button type="button" size="sm" onClick={() => analyzeInAssistant(file)}>Analyze with AI</Button>}
                  {file.url && <a href={file.url} target="_blank" rel="noreferrer" className="inline-flex min-h-10 items-center justify-center rounded-lg border px-3 text-sm font-semibold hover:bg-emerald-500/10">Open in Google</a>}
                </div>
              </div>
              {expanded && isForm && <div className="mt-4 min-w-0 border-t pt-4">
                {form ? <>
                  <h3 className="text-base font-semibold">{form.title}</h3>
                  {form.description && <p className="app-caption mt-1 whitespace-pre-wrap text-sm">{form.description}</p>}
                  <div className="mt-3 grid gap-2">{form.items.map((item, index) => <div key={`${file.id}-question-${index}`} className="rounded-lg border p-3"><p className="text-sm font-medium">{item.title || item.description || "Form section"}</p><p className="app-caption mt-1 text-xs">{googleFormItemSummary(item)}{item.questionItem?.question?.required ? " · Required" : ""}</p></div>)}</div>
                  {embedUrl && <details className="mt-4 rounded-lg border p-3"><summary className="cursor-pointer text-sm font-semibold">Show live Google Form</summary><p className="helper-text mt-2">This is the respondent-facing form. Submitting it will record a real response.</p><iframe className="mt-3 h-[780px] w-full rounded-lg border bg-white" src={embedUrl} title={`Live Google Form: ${form.title}`} loading="lazy" /></details>}
                  <div className="mt-4 flex flex-wrap gap-2"><Button type="button" variant="outline" size="sm" loading={busy === `responses-${file.id}`} onClick={() => void readDriveResponses(file.id)}>{responsePage ? "Refresh responses" : "Read responses"}</Button>{responsePage?.next_page_token && <Button type="button" variant="outline" size="sm" loading={busy === `responses-${file.id}`} onClick={() => void readDriveResponses(file.id, responsePage.next_page_token || undefined, true)}>Load more responses</Button>}</div>
                  {responsePage && <div className="mt-3 space-y-3"><p className="app-caption text-sm">Showing {responsePage.responses.length} response{responsePage.responses.length === 1 ? "" : "s"} from this page. Respondent email addresses are not displayed.</p>{!responsePage.responses.length && <p className="app-caption rounded-lg border p-3 text-sm">No responses are available yet.</p>}{responsePage.responses.map((response, responseIndex) => {
                    const submittedAt = response.lastSubmittedTime || response.createTime;
                    return <article key={`${file.id}-response-${responseIndex}`} className="rounded-lg border p-3"><p className="app-caption text-xs">{submittedAt ? `Submitted ${new Date(submittedAt).toLocaleString()}` : "Submission time unavailable"}</p><dl className="mt-2 grid gap-2">{Object.entries(response.answers || {}).map(([questionId, answer]) => <div key={questionId}><dt className="text-sm font-medium">{responsePage.question_titles[questionId] || `Question ${questionId}`}</dt><dd className="app-caption mt-0.5 whitespace-pre-wrap text-sm">{responseAnswerValues(answer).join(", ")}</dd></div>)}</dl></article>;
                  })}</div>}
                </> : <p className="app-caption text-sm">Loading the Form structure…</p>}
              </div>}
              {expanded && isSheet && <div className="mt-4 min-w-0 border-t pt-4">
                {sheet ? <>
                  <h3 className="text-base font-semibold">{sheet.title}</h3>
                  <div className="mt-3 flex flex-wrap gap-2">{sheet.sheets.map((tab) => <button key={tab.sheetId} type="button" aria-pressed={(googleSheetTabs[file.id] || sheet.sheets[0]?.title) === tab.title} className="rounded-lg border px-3 py-2 text-sm aria-pressed:border-emerald-500 aria-pressed:text-emerald-600" onClick={() => { setGoogleSheetTabs((current) => ({ ...current, [file.id]: tab.title })); void readDriveSheetValues(file.id, tab.title); }}>{tab.title}</button>)}</div>
                  <p className="helper-text mt-2">Showing up to 100 rows and 26 columns for the selected tab.</p>
                  {sheetData?.values.length ? <div className="mt-3 max-w-full overflow-auto rounded-lg border"><table className="min-w-full border-collapse text-left text-sm"><thead><tr>{sheetData.values[0].map((cell, cellIndex) => <th key={`head-${cellIndex}`} className="whitespace-nowrap border-b px-3 py-2 font-semibold">{String(cell ?? "")}</th>)}</tr></thead><tbody>{sheetData.values.slice(1).map((row, rowIndex) => <tr key={`row-${rowIndex}`} className="border-b last:border-0">{sheetData.values[0].map((_, cellIndex) => <td key={`cell-${rowIndex}-${cellIndex}`} className="max-w-80 whitespace-pre-wrap px-3 py-2 align-top">{String(row[cellIndex] ?? "")}</td>)}</tr>)}</tbody></table></div> : <p className="app-caption mt-3 rounded-lg border p-3 text-sm">{busy === `sheet-${file.id}` ? "Loading sheet values…" : "This tab is empty."}</p>}
                </> : <p className="app-caption text-sm">Loading spreadsheet details…</p>}
              </div>}
            </article>;
          })}
        </div>
        {driveNextPage && <Button type="button" variant="outline" className="mt-4" loading={driveLoading} onClick={() => void loadDriveFiles(driveQuery, driveType, driveNextPage, true)}>Load more files</Button>}
      </section>}

    {connected && <>
      <section className="mb-6 grid min-w-0 gap-4 xl:grid-cols-3">
        <form className="panel min-w-0 p-4" onSubmit={(event) => { event.preventDefault(); if (formTitle.trim()) void create("/api/v1/google-workspace/forms", { title: formTitle, description: formDescription }, "Google Form created."); }}>
          <h2 className="text-base font-semibold">New Google Form</h2>
          <label className="field-label mt-4" htmlFor="form-title">Title</label>
          <input id="form-title" value={formTitle} maxLength={250} onChange={(event) => setFormTitle(event.target.value)} required />
          <label className="field-label mt-3" htmlFor="form-description">Description <span className="app-caption font-normal">(optional)</span></label>
          <textarea id="form-description" value={formDescription} maxLength={10000} rows={3} onChange={(event) => setFormDescription(event.target.value)} />
          <Button className="mt-4 w-full" type="submit" loading={busy === "/api/v1/google-workspace/forms"}>Create form</Button>
        </form>
        <form className="panel min-w-0 p-4" onSubmit={(event) => { event.preventDefault(); if (sheetTitle.trim()) void create("/api/v1/google-workspace/spreadsheets", { title: sheetTitle }, "Google Sheet created."); }}>
          <h2 className="text-base font-semibold">New Google Sheet</h2>
          <label className="field-label mt-4" htmlFor="sheet-title">Title</label>
          <input id="sheet-title" value={sheetTitle} maxLength={250} onChange={(event) => setSheetTitle(event.target.value)} required />
          <p className="helper-text">Read and write cell values here, or open it in Google Sheets.</p>
          <Button className="mt-4 w-full" type="submit" loading={busy === "/api/v1/google-workspace/spreadsheets"}>Create sheet</Button>
        </form>
        <form className="panel min-w-0 p-4" onSubmit={(event) => { event.preventDefault(); if (folderTitle.trim()) void create("/api/v1/google-workspace/folders", { title: folderTitle }, "Drive folder created."); }}>
          <h2 className="text-base font-semibold">New Drive folder</h2>
          <label className="field-label mt-4" htmlFor="folder-title">Title</label>
          <input id="folder-title" value={folderTitle} maxLength={250} onChange={(event) => setFolderTitle(event.target.value)} required />
          <p className="helper-text">This app can manage folders it creates through the connected college account.</p>
          <Button className="mt-4 w-full" type="submit" loading={busy === "/api/v1/google-workspace/folders"}>Create folder</Button>
        </form>
      </section>

      <section aria-labelledby="resources-heading" className="min-w-0">
        <div className="mb-3 flex min-w-0 items-center justify-between gap-3"><h2 id="resources-heading" className="text-lg font-semibold">Managed resources</h2><span className="app-caption text-sm">{resources.length} total</span></div>
        {!resources.length && <div className="panel p-5"><p className="app-caption text-sm">No Google resources have been created through AntimBench yet.</p></div>}
        <div className="grid min-w-0 gap-4">
          {resources.map((resource) => <article key={resource.id} className="panel min-w-0 p-4 sm:p-5">
            <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-wide text-emerald-600">{typeLabel(resource.resource_type)}</p><a href={resource.url} target="_blank" rel="noreferrer" className="mt-1 block break-words text-base font-semibold hover:text-emerald-600">{resource.title}</a><p className="app-caption mt-1 text-xs">Created {new Date(resource.created_at).toLocaleString()}</p></div>
              <a href={resource.url} target="_blank" rel="noreferrer" className="inline-flex min-h-11 shrink-0 items-center justify-center rounded-lg border px-3 text-sm font-semibold hover:bg-emerald-500/10">Open in Google</a>
            </div>
            <div className="mt-4 grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
              <input aria-label={`Rename ${resource.title}`} value={draftTitles[resource.id] ?? resource.title} maxLength={250} onChange={(event) => setDraftTitles((current) => ({ ...current, [resource.id]: event.target.value }))} />
              <Button type="button" variant="outline" size="sm" loading={busy === `rename-${resource.id}`} onClick={() => void rename(resource)}>Rename</Button>
              <Button type="button" variant="danger" size="sm" loading={busy === `delete-${resource.id}`} onClick={() => void remove(resource)}>Delete</Button>
            </div>
            {resource.resource_type === "form" && <div className="mt-4"><Button type="button" variant="outline" size="sm" loading={busy === `responses-${resource.id}`} onClick={() => void readResponses(resource)}>Read responses</Button>{formResponses[resource.id] && <pre className="mt-3 max-h-64 max-w-full overflow-auto rounded-lg border p-3 text-xs">{JSON.stringify(formResponses[resource.id], null, 2)}</pre>}</div>}
            {resource.resource_type === "spreadsheet" && <div className="mt-4 grid min-w-0 gap-3"><div className="grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1fr)_auto]"><input aria-label={`Range for ${resource.title}`} value={rangeFor(resource)} onChange={(event) => setSheetRange((current) => ({ ...current, [resource.id]: event.target.value }))} /><Button type="button" variant="outline" size="sm" loading={busy === `read-sheet-${resource.id}`} onClick={() => void readSheet(resource)}>Read values</Button></div><label className="field-label" htmlFor={`sheet-values-${resource.id}`}>Values as JSON rows</label><textarea id={`sheet-values-${resource.id}`} rows={5} value={sheetValues[resource.id] ?? ""} placeholder={'[["Name", "Value"], ["Example", 1]]'} onChange={(event) => setSheetValues((current) => ({ ...current, [resource.id]: event.target.value }))} /><Button type="button" size="sm" className="w-full sm:w-fit" loading={busy === `write-sheet-${resource.id}`} onClick={() => void writeSheet(resource)}>Update sheet values</Button>{sheetPreview[resource.id] && <pre className="max-h-64 max-w-full overflow-auto rounded-lg border p-3 text-xs">{JSON.stringify(sheetPreview[resource.id], null, 2)}</pre>}</div>}
          </article>)}
        </div>
      </section>
    </>}
  <ConfirmDialog
    open={confirmation !== null}
    title={confirmation?.kind === "disconnect" ? "Disconnect this college from Google Workspace?" : "Delete this Google resource?"}
    description={confirmation?.kind !== "delete"
      ? "The college's Workspace connection will be removed. Existing Google files will remain in Drive."
      : "Permanently delete “" + confirmation.resource.title + "” from Google Workspace. This also removes its AntimBench link."}
    confirmLabel={confirmation?.kind === "disconnect" ? "Disconnect" : "Delete resource"}
    tone="danger"
    onClose={() => setConfirmation(null)}
    onConfirm={confirmDestructiveAction}
  />  </div>;
}
