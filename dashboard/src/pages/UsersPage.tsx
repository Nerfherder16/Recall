import { useState, useEffect } from "react";
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
          className="btn btn-primary btn-sm"
          onClick={() => setShowCreate(!showCreate)}
        >
          {showCreate ? "Cancel" : "Create User"}
        </button>
      </PageHeader>

      {/* Create user form */}
      {showCreate && (
        <div className="card bg-base-100 shadow-sm mb-4">
          <div className="card-body p-4">
            <div className="flex flex-wrap gap-3 items-end">
              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">Username</span>
                </label>
                <input
                  className="input input-bordered input-sm w-40"
                  placeholder="e.g. scott"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  pattern="[a-zA-Z0-9_-]+"
                />
              </div>
              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">Display Name</span>
                </label>
                <input
                  className="input input-bordered input-sm w-48"
                  placeholder="e.g. Scott M."
                  value={newDisplayName}
                  onChange={(e) => setNewDisplayName(e.target.value)}
                />
              </div>
              <label className="label cursor-pointer gap-2">
                <input
                  type="checkbox"
                  className="checkbox checkbox-sm"
                  checked={newIsAdmin}
                  onChange={(e) => setNewIsAdmin(e.target.checked)}
                />
                <span className="label-text text-xs">Admin</span>
              </label>
              <button
                className={`btn btn-primary btn-sm ${creating ? "loading" : ""}`}
                onClick={createUser}
                disabled={!newUsername.trim() || creating}
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* API key reveal modal */}
      {createdKey && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">API Key Created</h3>
            <p className="py-2 text-sm text-warning">
              Copy this key now. It will not be shown again.
            </p>
            <div className="bg-base-200 p-3 rounded-lg font-mono text-sm break-all select-all">
              {createdKey}
            </div>
            <div className="modal-action">
              <button
                className="btn btn-sm"
                onClick={() => {
                  navigator.clipboard.writeText(createdKey);
                  addToast("Key copied to clipboard", "success");
                }}
              >
                Copy
              </button>
              <button
                className="btn btn-primary btn-sm"
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
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead>
              <tr>
                <th>Username</th>
                <th>Display Name</th>
                <th>Admin</th>
                <th>Created</th>
                <th>Last Active</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="font-medium">{u.username}</td>
                  <td className="text-base-content/60">
                    {u.display_name || "-"}
                  </td>
                  <td>
                    {u.is_admin && (
                      <span className="badge badge-xs badge-warning">
                        admin
                      </span>
                    )}
                  </td>
                  <td className="text-xs text-base-content/50">
                    {timeAgo(u.created_at)}
                  </td>
                  <td className="text-xs text-base-content/50">
                    {timeAgo(u.last_active_at)}
                  </td>
                  <td>
                    <button
                      className="btn btn-ghost btn-xs text-error"
                      onClick={() => setConfirmDelete(u.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Delete User"
        message="Are you sure? The user's memories will remain but they won't be able to authenticate."
        confirmLabel="Delete"
        onConfirm={() => confirmDelete !== null && deleteUser(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
