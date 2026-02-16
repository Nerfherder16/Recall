import { useState, useEffect } from "react";
import { Plus, Trash, Copy, X } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { UserInfo, CreateUserResponse } from "../api/types";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToastContext } from "../context/ToastContext";

export default function UsersPage() {
  const { addToast } = useToastContext();
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  useEffect(() => {
    loadUsers();
  }, []);

  async function loadUsers() {
    setLoading(true);
    try {
      const data = await api<UserInfo[]>("/admin/users");
      setUsers(data);
    } catch {
      addToast("Failed to load users", "error");
    } finally {
      setLoading(false);
    }
  }

  async function createUser() {
    if (!newUsername.trim()) return;
    setCreating(true);
    try {
      const res = await api<CreateUserResponse>("/admin/users", "POST", {
        username: newUsername.trim(),
        display_name: newDisplayName.trim() || null,
        is_admin: newIsAdmin,
      });
      setCreatedKey(res.api_key);
      setUsers((prev) => [
        ...prev,
        {
          id: res.id,
          username: res.username,
          display_name: res.display_name,
          is_admin: res.is_admin,
          created_at: res.created_at,
          last_active_at: res.last_active_at,
        },
      ]);
      setNewUsername("");
      setNewDisplayName("");
      setNewIsAdmin(false);
      addToast(`User "${res.username}" created`, "success");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to create user";
      addToast(msg, "error");
    } finally {
      setCreating(false);
    }
  }

  async function deleteUser(id: number) {
    setConfirmDelete(null);
    try {
      await api(`/admin/users/${id}`, "DELETE");
      setUsers((prev) => prev.filter((u) => u.id !== id));
      addToast("User deleted", "success");
    } catch {
      addToast("Failed to delete user", "error");
    }
  }

  function timeAgo(iso: string | null): string {
    if (!iso) return "never";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }

  return (
    <div>
      <PageHeader title="Users" subtitle="Manage API keys and user identities">
        <button
          className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-content hover:bg-primary/90 transition-colors"
          onClick={() => setShowCreate(!showCreate)}
        >
          {showCreate ? (
            <>
              <X size={14} /> Cancel
            </>
          ) : (
            <>
              <Plus size={14} /> Create User
            </>
          )}
        </button>
      </PageHeader>

      {/* Create user form */}
      {showCreate && (
        <div className="rounded-xl bg-base-100 border border-base-content/5 p-4 mb-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wider text-base-content/40 mb-1">
                Username
              </label>
              <input
                className="rounded-lg border border-base-content/10 bg-base-200 px-3 py-1.5 text-sm focus:border-primary/50 focus:outline-none w-40"
                placeholder="e.g. scott"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                pattern="[a-zA-Z0-9_-]+"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wider text-base-content/40 mb-1">
                Display Name
              </label>
              <input
                className="rounded-lg border border-base-content/10 bg-base-200 px-3 py-1.5 text-sm focus:border-primary/50 focus:outline-none w-48"
                placeholder="e.g. Scott M."
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
              />
            </div>
            <label className="flex items-center gap-2 cursor-pointer py-1.5">
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={newIsAdmin}
                onChange={(e) => setNewIsAdmin(e.target.checked)}
              />
              <span className="text-sm">Admin</span>
            </label>
            <button
              className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-primary-content hover:bg-primary/90 transition-colors disabled:opacity-50"
              onClick={createUser}
              disabled={!newUsername.trim() || creating}
            >
              Create
            </button>
          </div>
        </div>
      )}

      {/* API key reveal modal */}
      {createdKey && (
        <div className="modal modal-open">
          <div className="rounded-2xl bg-base-100 border border-base-content/5 p-6 max-w-md w-full">
            <h3 className="font-semibold text-lg">API Key Created</h3>
            <p className="py-2 text-sm text-amber-400">
              Copy this key now. It will not be shown again.
            </p>
            <div className="bg-base-200 border border-base-content/5 p-3 rounded-lg font-mono text-sm break-all select-all">
              {createdKey}
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm hover:bg-base-content/5 transition-colors"
                onClick={() => {
                  navigator.clipboard.writeText(createdKey);
                  addToast("Key copied to clipboard", "success");
                }}
              >
                <Copy size={14} />
                Copy
              </button>
              <button
                className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-primary-content hover:bg-primary/90 transition-colors"
                onClick={() => setCreatedKey(null)}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {loading && <LoadingSpinner />}

      {!loading && users.length === 0 && (
        <EmptyState message="No users yet. Create one to get started." />
      )}

      {!loading && users.length > 0 && (
        <div className="rounded-xl bg-base-100 border border-base-content/5 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-base-content/5">
                  <th className="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Username
                  </th>
                  <th className="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Display Name
                  </th>
                  <th className="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Admin
                  </th>
                  <th className="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Created
                  </th>
                  <th className="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Last Active
                  </th>
                  <th className="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr
                    key={u.id}
                    className="border-b border-base-content/5 last:border-0"
                  >
                    <td className="px-4 py-2.5 font-medium">{u.username}</td>
                    <td className="px-4 py-2.5 text-base-content/50">
                      {u.display_name || "-"}
                    </td>
                    <td className="px-4 py-2.5">
                      {u.is_admin && (
                        <span className="inline-flex items-center rounded-md bg-amber-500/10 text-amber-400 px-2 py-0.5 text-[11px] font-medium">
                          admin
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-base-content/40">
                      {timeAgo(u.created_at)}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-base-content/40">
                      {timeAgo(u.last_active_at)}
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        className="rounded-lg p-1.5 text-base-content/30 hover:text-error hover:bg-error/10 transition-colors"
                        onClick={() => setConfirmDelete(u.id)}
                        title="Delete user"
                      >
                        <Trash size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Delete User"
        message="Are you sure? The user's memories will remain but they won't be able to authenticate."
        confirmLabel="Delete"
        confirmClass="btn-error"
        onConfirm={() => confirmDelete !== null && deleteUser(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
