import { useState, useEffect } from "react";
import { Plus, Trash, Copy, X } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { UserInfo, CreateUserResponse } from "../api/types";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToastContext } from "../context/ToastContext";
import { GlassCard } from "../components/common/GlassCard";
import { Button } from "../components/common/Button";
import { Input } from "../components/common/Input";
import { Checkbox } from "../components/common/Checkbox";
import { Modal } from "../components/common/Modal";
import { timeAgo } from "../lib/utils";

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

  return (
    <div>
      <PageHeader title="Users" subtitle="Manage API keys and user identities">
        <Button
          size="sm"
          variant={showCreate ? "ghost" : "primary"}
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
        </Button>
      </PageHeader>

      {/* Create user form */}
      {showCreate && (
        <GlassCard className="p-4 mb-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="block font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500 mb-1">
                Username
              </label>
              <Input
                containerClass="w-40"
                placeholder="e.g. scott"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
              />
            </div>
            <div>
              <label className="block font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500 mb-1">
                Display Name
              </label>
              <Input
                containerClass="w-48"
                placeholder="e.g. Scott M."
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
              />
            </div>
            <Checkbox
              label="Admin"
              checked={newIsAdmin}
              onChange={(e) => setNewIsAdmin(e.target.checked)}
            />
            <Button
              onClick={createUser}
              disabled={!newUsername.trim() || creating}
              loading={creating}
            >
              Create
            </Button>
          </div>
        </GlassCard>
      )}

      {/* API key reveal modal */}
      <Modal open={!!createdKey} onClose={() => setCreatedKey(null)}>
        <h3 className="font-display font-semibold text-lg text-zinc-900 dark:text-zinc-100">
          API Key Created
        </h3>
        <p className="py-2 text-sm text-amber-500 dark:text-amber-400">
          Copy this key now. It will not be shown again.
        </p>
        <div className="bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-white/[0.06] p-3 rounded-xl font-mono text-sm text-zinc-900 dark:text-zinc-100 break-all select-all">
          {createdKey}
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              if (createdKey) {
                navigator.clipboard.writeText(createdKey);
                addToast("Key copied to clipboard", "success");
              }
            }}
          >
            <Copy size={14} />
            Copy
          </Button>
          <Button size="sm" onClick={() => setCreatedKey(null)}>
            Done
          </Button>
        </div>
      </Modal>

      {loading && <LoadingSpinner />}

      {!loading && users.length === 0 && (
        <EmptyState message="No users yet. Create one to get started." />
      )}

      {!loading && users.length > 0 && (
        <GlassCard className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-white/[0.06]">
                  {[
                    "Username",
                    "Display Name",
                    "Admin",
                    "Created",
                    "Last Active",
                    "",
                  ].map((h) => (
                    <th
                      key={h || "actions"}
                      className="text-left px-4 py-2.5 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr
                    key={u.id}
                    className="border-b border-zinc-100 dark:border-white/[0.03] last:border-0"
                  >
                    <td className="px-4 py-2.5 font-medium text-zinc-900 dark:text-zinc-100">
                      {u.username}
                    </td>
                    <td className="px-4 py-2.5 text-zinc-500 dark:text-zinc-400">
                      {u.display_name || "-"}
                    </td>
                    <td className="px-4 py-2.5">
                      {u.is_admin && (
                        <span className="inline-flex items-center rounded-full bg-amber-500/10 text-amber-400 px-2 py-0.5 text-[11px] font-medium ring-1 ring-amber-500/20">
                          admin
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-zinc-400 dark:text-zinc-500">
                      {timeAgo(u.created_at)}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-zinc-400 dark:text-zinc-500">
                      {u.last_active_at ? timeAgo(u.last_active_at) : "never"}
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        className="rounded-lg p-1.5 text-zinc-400 dark:text-zinc-500 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-500/10 transition-colors"
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
        </GlassCard>
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
