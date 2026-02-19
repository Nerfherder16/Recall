import { useState, useCallback, useEffect, useRef } from "react";
import {
  FilePdf,
  FileText,
  FileCode,
  Trash,
  PushPin,
  PushPinSlash,
  UploadSimple,
  Lock,
  ShieldCheck,
} from "@phosphor-icons/react";
import { api, apiUpload } from "../api/client";
import type {
  DocumentEntry,
  DocumentDetail,
  IngestResponse,
} from "../api/types";
import { useToastContext } from "../context/ToastContext";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import ConfirmDialog from "../components/ConfirmDialog";
import { GlassCard } from "../components/common/GlassCard";
import { Button } from "../components/common/Button";
import { Input, Select } from "../components/common/Input";

const FILE_TYPE_ICONS: Record<string, typeof FilePdf> = {
  pdf: FilePdf,
  markdown: FileCode,
  text: FileText,
};

function DurabilityBadge({ durability }: { durability: string | null }) {
  if (durability === "permanent")
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20">
        <Lock size={10} /> Permanent
      </span>
    );
  if (durability === "durable")
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/20">
        <ShieldCheck size={10} /> Durable
      </span>
    );
  return null;
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DocumentEntry | null>(null);
  const [uploadDomain, setUploadDomain] = useState("general");
  const [uploadDurability, setUploadDurability] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const { addToast } = useToastContext();

  const fetchDocs = useCallback(async () => {
    try {
      const data = await api<DocumentEntry[]>("/document/");
      setDocs(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load";
      addToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  const handleUpload = useCallback(async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("domain", uploadDomain);
      if (uploadDurability) fd.append("durability", uploadDurability);
      const res = await apiUpload<IngestResponse>("/document/ingest", fd);
      addToast(
        `Ingested "${res.document.filename}" — ${res.memories_created} memories`,
        "success",
      );
      if (fileRef.current) fileRef.current.value = "";
      await fetchDocs();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      addToast(msg, "error");
    } finally {
      setUploading(false);
    }
  }, [uploadDomain, uploadDurability, addToast, fetchDocs]);

  const handleDelete = useCallback(
    async (doc: DocumentEntry) => {
      try {
        await api(`/document/${doc.id}`, "DELETE");
        addToast(`Deleted "${doc.filename}"`, "success");
        setDocs((prev) => prev.filter((d) => d.id !== doc.id));
        setDeleteTarget(null);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Delete failed";
        addToast(msg, "error");
      }
    },
    [addToast],
  );

  const handlePin = useCallback(
    async (doc: DocumentEntry) => {
      const method = doc.pinned ? "DELETE" : "POST";
      try {
        await api(`/document/${doc.id}/pin`, method);
        addToast(doc.pinned ? "Unpinned" : "Pinned", "success");
        await fetchDocs();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Pin failed";
        addToast(msg, "error");
      }
    },
    [addToast, fetchDocs],
  );

  const handleExpand = useCallback(
    async (docId: string) => {
      if (expandedId === docId) {
        setExpandedId(null);
        setDetail(null);
        return;
      }
      setExpandedId(docId);
      try {
        const d = await api<DocumentDetail>(`/document/${docId}`);
        setDetail(d);
      } catch {
        setDetail(null);
      }
    },
    [expandedId],
  );

  if (loading) return <LoadingSpinner />;

  return (
    <div>
      <PageHeader
        title="Documents"
        subtitle={`${docs.length} document${docs.length !== 1 ? "s" : ""} ingested`}
      />

      {/* Upload bar */}
      <GlassCard className="p-4 mb-6">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="block font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500 mb-1">
              File
            </label>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.md,.markdown,.txt,.text,.log,.csv,.json,.yaml,.yml"
              className="w-full rounded-xl border border-zinc-200 dark:border-white/[0.06] bg-zinc-100 dark:bg-zinc-900/80 px-3 py-1.5 text-sm text-zinc-900 dark:text-zinc-100 file:mr-3 file:rounded-lg file:border-0 file:bg-violet-600 file:px-3 file:py-1 file:text-xs file:font-medium file:text-white hover:file:bg-violet-500 file:cursor-pointer focus:border-violet-500/50 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
            />
          </div>
          <div>
            <label className="block font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500 mb-1">
              Domain
            </label>
            <Input
              value={uploadDomain}
              onChange={(e) => setUploadDomain(e.target.value)}
              containerClass="w-32"
              placeholder="general"
            />
          </div>
          <div>
            <label className="block font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500 mb-1">
              Durability
            </label>
            <Select
              value={uploadDurability}
              onChange={(e) => setUploadDurability(e.target.value)}
              containerClass="w-36"
            >
              <option value="">Auto</option>
              <option value="ephemeral">Ephemeral</option>
              <option value="durable">Durable</option>
              <option value="permanent">Permanent</option>
            </Select>
          </div>
          <Button
            size="sm"
            onClick={handleUpload}
            disabled={uploading}
            loading={uploading}
          >
            {!uploading && <UploadSimple size={14} />}
            {uploading ? "Ingesting..." : "Upload"}
          </Button>
        </div>
      </GlassCard>

      {/* Document cards */}
      {docs.length === 0 ? (
        <p className="text-sm text-zinc-400 dark:text-zinc-500 text-center py-12">
          No documents ingested yet. Upload a file above.
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {docs.map((doc) => {
            const IconComp = FILE_TYPE_ICONS[doc.file_type] || FileText;
            const isExpanded = expandedId === doc.id;
            return (
              <GlassCard
                key={doc.id}
                hover
                className={`p-4 cursor-pointer ${isExpanded ? "col-span-full" : ""}`}
                onClick={() => handleExpand(doc.id)}
              >
                <div className="flex items-start gap-3">
                  <IconComp
                    size={28}
                    className="text-violet-600 dark:text-violet-400 shrink-0 mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100 truncate">
                      {doc.filename}
                    </h3>
                    <div className="flex flex-wrap items-center gap-1.5 mt-1">
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 ring-1 ring-violet-500/20">
                        {doc.domain}
                      </span>
                      <span className="text-[10px] text-zinc-400 dark:text-zinc-500">
                        {doc.memory_count} memories
                      </span>
                      <DurabilityBadge durability={doc.durability} />
                      {doc.pinned && (
                        <span className="text-[10px] text-amber-400">
                          <PushPin size={10} weight="fill" />
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-zinc-400 dark:text-zinc-600 mt-1">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div
                    className="flex gap-1 shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handlePin(doc)}
                      title={doc.pinned ? "Unpin" : "Pin"}
                    >
                      {doc.pinned ? (
                        <PushPinSlash size={14} />
                      ) : (
                        <PushPin size={14} />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-500 dark:text-red-400 hover:bg-red-500/10"
                      onClick={() => setDeleteTarget(doc)}
                      title="Delete"
                    >
                      <Trash size={14} />
                    </Button>
                  </div>
                </div>

                {/* Expanded detail */}
                {isExpanded && detail && detail.id === doc.id && (
                  <div className="mt-4 border-t border-zinc-200 dark:border-white/[0.06] pt-3">
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-2">
                      {detail.child_memory_ids.length} child memories
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {detail.child_memory_ids.slice(0, 20).map((cid) => (
                        <span
                          key={cid}
                          className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400"
                        >
                          {cid.slice(0, 8)}...
                        </span>
                      ))}
                      {detail.child_memory_ids.length > 20 && (
                        <span className="text-[9px] text-zinc-400 dark:text-zinc-500">
                          +{detail.child_memory_ids.length - 20} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </GlassCard>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Document"
        message={
          deleteTarget
            ? `Delete "${deleteTarget.filename}" and all ${deleteTarget.memory_count} child memories? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        onConfirm={() => deleteTarget && handleDelete(deleteTarget)}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
