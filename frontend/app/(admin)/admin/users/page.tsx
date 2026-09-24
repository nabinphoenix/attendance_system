"use client";

import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { UnlockAccountButton } from "@/components/UnlockAccountButton";

type User = {
  id: number;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  is_locked: boolean;
  failed_login_attempts: number;
};

const roles = ["student", "teacher", "admin", "coordinator", "parent"];

export default function Page() {
  const [users, setUsers] = useState<User[]>([]);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState<number | null>(null);

  async function load() {
    try {
      setUsers((await api.get("/api/v1/users")).data);
    } catch (e: any) {
      setError(e.response?.data?.detail ?? "Unable to load users");
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filteredUsers = useMemo(() => {
    const term = search.trim().toLowerCase();
    return users.filter((user) => {
      const matchesSearch =
        !term ||
        user.name.toLowerCase().includes(term) ||
        user.email.toLowerCase().includes(term);
      const matchesRole = roleFilter === "all" || user.role === roleFilter;
      return matchesSearch && matchesRole;
    });
  }, [roleFilter, search, users]);

  async function update(id: number, values: object) {
    setSaving(id);
    setError("");
    try {
      await api.patch(`/api/v1/users/${id}`, values);
      await load();
    } catch (e: any) {
      setError(e.response?.data?.detail ?? "Unable to update user");
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="max-w-6xl">
      <h1 className="mb-2 text-3xl font-bold">User access</h1>
      <p className="mb-6 text-slate-400">
        Manage account roles and access. Inactive accounts cannot sign in.
      </p>

      {error && <p className="mb-4 text-red-400">{error}</p>}

      <div className="mb-4 flex flex-col gap-3 sm:flex-row">
        <label className="flex-1">
          <span className="sr-only">Search by name or email</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by name or email"
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-emerald-400"
          />
        </label>
        <label>
          <span className="sr-only">Filter by role</span>
          <select
            aria-label="Filter by role"
            value={roleFilter}
            onChange={(event) => setRoleFilter(event.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm capitalize outline-none focus:border-emerald-400 sm:w-48"
          >
            <option value="all">All roles</option>
            {roles.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="mb-3 text-sm text-slate-500">
        Showing {filteredUsers.length} of {users.length} users
      </p>

      <div
        className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900"
        role="region"
        aria-label="Scrollable records"
        tabIndex={0}
      >
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-slate-400">
              <th className="p-3">Name</th>
              <th className="p-3">Email</th>
              <th className="p-3">Role</th>
              <th className="p-3">Status</th>
              <th className="p-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.map((user) => (
              <tr key={user.id} className="border-b border-slate-800">
                <td className="p-3">{user.name}</td>
                <td className="p-3">{user.email}</td>
                <td className="p-3">
                  <select
                    aria-label={`Role for ${user.name}`}
                    className="rounded bg-slate-950 p-2"
                    value={user.role}
                    disabled={saving === user.id}
                    onChange={(event) =>
                      update(user.id, { role: event.target.value })
                    }
                  >
                    {roles.map((role) => (
                      <option key={role}>{role}</option>
                    ))}
                  </select>
                </td>
                <td className="p-3">
                  {user.is_locked && (
                    <p className="font-semibold text-red-500">Locked</p>
                  )}
                  <p className="text-xs text-slate-400">
                    Failed attempts: {user.failed_login_attempts}
                  </p>
                  <span
                    className={
                      user.is_active ? "text-emerald-400" : "text-amber-400"
                    }
                  >
                    {user.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="p-3">
                  <div className="flex flex-wrap gap-2">
                    {user.is_locked && (
                      <UnlockAccountButton
                        id={user.id}
                        name={user.name}
                        onUnlocked={load}
                      />
                    )}
                    <Button
                      className="text-sm"
                      disabled={saving === user.id}
                      onClick={() =>
                        update(user.id, { is_active: !user.is_active })
                      }
                    >
                      {user.is_active ? "Deactivate" : "Reactivate"}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {!filteredUsers.length && (
              <tr>
                <td colSpan={5} className="p-5 text-center text-slate-400">
                  {users.length
                    ? "No users match these filters."
                    : "No users found."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
