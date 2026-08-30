"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { type Role } from "@/lib/auth";
import RoleShell from "@/components/RoleShell";
import ProfileAvatar from "@/components/ProfileAvatar";
import { useTheme } from "@/components/ThemeProvider";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { Button } from "@/components/ui/Button";

type User = { id: number; name: string; email: string; role: Role; avatar_url?: string | null };

function Notice({ message, tone = "success" }: { message: string; tone?: "success" | "error" }) {
  return <div role={tone === "error" ? "alert" : "status"} className={`rounded-xl border p-3 text-sm ${tone === "error" ? "border-red-500/30 bg-red-500/10 text-red-600" : "border-emerald-500/30 bg-emerald-500/10 text-emerald-700"}`}>{message}</div>;
}

async function uploadFailure(response: Response) {
  const fallback = `The server could not upload this image (HTTP ${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      const messages = body.detail.map((item: unknown) => (
        typeof item === "object" && item !== null && "msg" in item && typeof item.msg === "string" ? item.msg : ""
      )).filter(Boolean);
      return messages.join(" ") || fallback;
    }
  } catch {
    // A proxy or server error may not have a JSON response body.
  }
  return fallback;
}

function SettingsScreen({ initialUser }: { initialUser: User }) {
  const { theme, setTheme } = useTheme();
  const [user, setUser] = useState(initialUser);
  const [name, setName] = useState(initialUser.name);
  const [email, setEmail] = useState(initialUser.email);
  const [emailChangePassword, setEmailChangePassword] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [profileMessage, setProfileMessage] = useState("");
  const [profileError, setProfileError] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordError, setPasswordError] = useState("");

  function announceProfile(nextUser: User) {
    setUser(nextUser);
    setName(nextUser.name);
    setEmail(nextUser.email);
    window.dispatchEvent(new CustomEvent("antimbench-profile-updated", { detail: nextUser }));
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setProfileError(""); setProfileMessage("");
    if (!name.trim()) { setProfileError("Enter the name you would like to use."); return; }
    const normalizedEmail = email.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) { setProfileError("Enter a valid email address."); return; }
    const emailChanged = normalizedEmail !== user.email.toLowerCase();
    if (emailChanged && !emailChangePassword) { setProfileError("Enter your current password to change your sign-in email."); return; }
    setSavingProfile(true);
    try {
      const response = await api.patch<User>("/api/v1/auth/me", {
        name: name.trim(),
        email: normalizedEmail,
        ...(emailChanged ? { current_password: emailChangePassword } : {}),
      });
      announceProfile(response.data);
      setEmailChangePassword("");
      setProfileMessage("Your profile details have been saved.");
    } catch (error: any) {
      setProfileError(error.response?.data?.detail ?? "We could not save your profile. Please try again.");
    } finally { setSavingProfile(false); }
  }

  async function uploadPhoto(event: ChangeEvent<HTMLInputElement>) {
    const image = event.target.files?.[0];
    event.target.value = "";
    if (!image) return;
    setProfileError(""); setProfileMessage("");
    if (image.size > 5 * 1024 * 1024) { setProfileError("Choose an image smaller than 5 MB."); return; }
    const formData = new FormData(); formData.append("image", image, image.name);
    setUploading(true);
    try {
      // Upload through the Next.js proxy so the browser always sends the
      // current same-origin session cookie and sets the multipart boundary.
      const response = await fetch("/api/v1/auth/me/avatar", {
        method: "POST",
        body: formData,
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(await uploadFailure(response));
      announceProfile(await response.json() as User);
      setProfileMessage("Your profile photo has been updated.");
    } catch (error: unknown) {
      setProfileError(error instanceof Error ? error.message : "We could not upload that image. Please try again.");
    } finally { setUploading(false); }
  }

  async function savePassword(event: FormEvent) {
    event.preventDefault();
    setPasswordError(""); setPasswordMessage("");
    if (newPassword.length < 8) { setPasswordError("Your new password must be at least 8 characters."); return; }
    if (newPassword !== confirmPassword) { setPasswordError("The two new passwords do not match."); return; }
    setSavingPassword(true);
    try {
      await api.post("/api/v1/auth/me/password", { current_password: currentPassword, new_password: newPassword });
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      setPasswordMessage("Your password has been changed.");
    } catch (error: any) {
      setPasswordError(error.response?.data?.detail ?? "We could not change your password. Check your current password and try again.");
    } finally { setSavingPassword(false); }
  }

  return <div>
    <header className="mb-7"><p className="text-sm font-semibold uppercase tracking-[.15em] text-emerald-600">Account</p><h1 className="mt-2 text-3xl font-semibold">Personal settings</h1><p className="app-caption mt-2 max-w-2xl">Manage how your profile appears, choose your preferred workspace theme, and keep your account secure.</p></header>
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,.72fr)]">
      <div className="space-y-6">
        <section className="panel p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-4"><ProfileAvatar name={user.name} src={user.avatar_url} className="h-20 w-20 text-2xl" /><div className="min-w-0 flex-1"><h2 className="text-lg font-semibold">Profile photo</h2><p className="app-caption mt-1 text-sm">Use a clear photo so your classmates and team can recognize you.</p></div><label className="inline-flex min-h-10 cursor-pointer items-center justify-center rounded-lg border border-emerald-600 bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700"><input className="sr-only" type="file" accept="image/jpeg,image/jpg,image/png,image/webp" onChange={uploadPhoto} disabled={uploading} />{uploading ? "Uploading…" : "Upload photo"}</label></div>
          <p className="app-caption mt-4 text-xs">JPG, PNG, or WEBP · Maximum file size 5 MB</p>
          {profileError && <div className="mt-4"><Notice message={profileError} tone="error" /></div>}{profileMessage && <div className="mt-4"><Notice message={profileMessage} /></div>}
        </section>

        <form onSubmit={saveProfile} className="panel p-5 sm:p-6">
          <div className="mb-5"><h2 className="text-lg font-semibold">Profile details</h2><p className="app-caption mt-1 text-sm">Update the name and email address used across your AntimBench workspace.</p></div>
          <div className="grid gap-4 sm:grid-cols-2"><label><span className="field-label">Display name</span><input value={name} maxLength={150} onChange={(event) => setName(event.target.value)} autoComplete="name" className="w-full" /></label><label><span className="field-label">College email</span><input value={email} type="email" onChange={(event) => setEmail(event.target.value)} autoComplete="email" className="w-full" aria-describedby="email-note" /><span id="email-note" className="helper-text">Changing your sign-in email requires your current password.</span></label>{email.trim().toLowerCase() !== user.email.toLowerCase() && <label className="sm:col-span-2"><span className="field-label">Current password to confirm email change</span><PasswordInput value={emailChangePassword} onChange={(event) => setEmailChangePassword(event.target.value)} required autoComplete="current-password" className="w-full" /></label>}</div>
          <div className="mt-5 flex justify-end"><Button type="submit" loading={savingProfile}>{savingProfile ? "Saving…" : "Save profile"}</Button></div>
        </form>

        <form onSubmit={savePassword} className="panel p-5 sm:p-6">
          <div className="mb-5"><h2 className="text-lg font-semibold">Password &amp; security</h2><p className="app-caption mt-1 text-sm">Choose a strong password you do not use anywhere else.</p></div>
          {passwordError && <div className="mb-4"><Notice message={passwordError} tone="error" /></div>}{passwordMessage && <div className="mb-4"><Notice message={passwordMessage} /></div>}
          <div className="grid gap-4"><label><span className="field-label">Current password</span><PasswordInput value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required autoComplete="current-password" className="w-full" /></label><div className="grid gap-4 sm:grid-cols-2"><label><span className="field-label">New password</span><PasswordInput value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required minLength={8} autoComplete="new-password" className="w-full" /></label><label><span className="field-label">Confirm new password</span><PasswordInput value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required minLength={8} autoComplete="new-password" className="w-full" /></label></div></div>
          <div className="mt-5 flex justify-end"><Button type="submit" loading={savingPassword}>{savingPassword ? "Updating…" : "Change password"}</Button></div>
        </form>
      </div>

      <aside className="space-y-6">
        <section className="panel p-5 sm:p-6"><p className="text-sm font-semibold uppercase tracking-[.12em] text-emerald-600">Appearance</p><h2 className="mt-2 text-lg font-semibold">Your workspace, your light</h2><p className="app-caption mt-2 text-sm leading-6">Your preference follows you across the landing page and every dashboard on this browser.</p><div className="mt-5 grid grid-cols-2 gap-3"><button type="button" onClick={() => setTheme("light")} className={`rounded-xl border p-3 text-left transition ${theme === "light" ? "border-emerald-500 bg-emerald-500/10 ring-1 ring-emerald-500" : "border-slate-700 hover:border-emerald-500/50"}`} aria-pressed={theme === "light"}><span className="mb-3 block h-10 rounded-lg border border-slate-200 bg-white shadow-sm" /><span className="block text-sm font-semibold">Light</span><span className="app-caption mt-1 block text-xs">Clear and bright</span></button><button type="button" onClick={() => setTheme("dark")} className={`rounded-xl border p-3 text-left transition ${theme === "dark" ? "border-emerald-500 bg-emerald-500/10 ring-1 ring-emerald-500" : "border-slate-700 hover:border-emerald-500/50"}`} aria-pressed={theme === "dark"}><span className="mb-3 block h-10 rounded-lg border border-slate-700 bg-slate-950 shadow-sm" /><span className="block text-sm font-semibold">Dark</span><span className="app-caption mt-1 block text-xs">Easy on the eyes</span></button></div></section>
        <section className="panel p-5 sm:p-6"><p className="text-sm font-semibold uppercase tracking-[.12em] text-emerald-600">Account summary</p><dl className="mt-4 space-y-4 text-sm"><div className="flex justify-between gap-4"><dt className="app-caption">Access level</dt><dd className="font-semibold capitalize">{user.role}</dd></div><div className="flex justify-between gap-4"><dt className="app-caption">Sign-in email</dt><dd className="max-w-[13rem] truncate font-semibold" title={user.email}>{user.email}</dd></div><div className="flex justify-between gap-4"><dt className="app-caption">Profile photo</dt><dd className="font-semibold">{user.avatar_url ? "Added" : "Not added"}</dd></div></dl></section>
      </aside>
    </div>
  </div>;
}

export default function Page() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.get<User>("/api/v1/auth/me").then((response) => setUser(response.data)).catch((requestError) => { if (requestError.response?.status === 401) router.replace("/login"); else setError("We could not load your account. Please sign in again."); }); }, [router]);
  if (error) return <main className="grid min-h-screen place-items-center px-5"><div className="panel max-w-md p-6 text-center"><h1 className="text-xl font-semibold">Account unavailable</h1><p className="app-caption mt-2 text-sm">{error}</p></div></main>;
  if (!user) return <main className="grid min-h-screen place-items-center"><span className="h-9 w-9 animate-spin rounded-full border-2 border-emerald-500 border-r-transparent" aria-label="Loading settings" /></main>;
  return <RoleShell role={user.role}><SettingsScreen initialUser={user} /></RoleShell>;
}
