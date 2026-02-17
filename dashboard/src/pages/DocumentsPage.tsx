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
import { useToast } from "../hooks/useToast";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import ConfirmDialog from "../components/ConfirmDialog";

const FILE_TYPE_ICONS: Record<string, typeof FilePdf> = {
  pdf: FilePdf,
  markdown: FileCode,
  text: FileText,
};

function DurabilityBadge({ durability }: { durability: string | null }) {
  if (durability === "permanent")
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400">
        <Lock size={10} /> Permanent
      </span>
    );
  if (durability === "durable")
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400">
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
  const { addToast } = useToast();

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
      <div className="flex flex-wrap items-end gap-3 mb-6 p-4 rounded-xl border border-base-content/5 bg-base-200/30">
        <div className="flex-1 min-w-[200px]">
          <label className="text-xs text-base-content/50 mb-1 block">
            File
          </label>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.md,.markdown,.txt,.text,.log,.csv,.json,.yaml,.yml"
            className="file-input file-input-bordered file-input-sm w-full"
          />
        </div>
        <div>
          <label className="text-xs text-base-content/50 mb-1 block">
            Domain
          </label>
          <input
            value={uploadDomain}
            onChange={(e) => setUploadDomain(e.target.value)}
            className="input input-bordered input-sm w-32"
            placeholder="general"
          />
        </div>
        <div>
          <label className="text-xs text-base-content/50 mb-1 block">
            Durability
          </label>
          <select
            value={uploadDurability}
            onChange={(e) => setUploadDurability(e.target.value)}
            className="select select-bordered select-sm w-36"
          >
            <option value="">Auto</option>
            <option value="ephemeral">Ephemeral</option>
            <option value="durable">Durable</option>
            <option value="permanent">Permanent</option>
          </select>
        </div>
        <button
          className="btn btn-primary btn-sm gap-1"
          onClick={handleUpload}
          disabled={uploading}
        >
          {uploading ? (
            <span className="loading loading-spinner loading-xs" />
          ) : (
            <UploadSimple size={14} />
          )}
          {uploading ? "Ingesting..." : "Upload"}
        </button>
      </div>

      {/* Document cards */}
      {docs.length === 0 ? (
        <p className="text-sm text-base-content/40 text-center py-12">
          No documents ingested yet. Upload a file above.
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {docs.map((doc) => {
            const IconComp = FILE_TYPE_ICONS[doc.file_type] || FileText;
            const isExpanded = expandedId === doc.id;
            return (
              <div
                key={doc.id}
                className={`rounded-xl border border-base-content/5 bg-base-200/30 p-4 transition-all cursor-pointer hover:border-base-content/10 ${
                  isExpanded ? "col-span-full" : ""
                }`}
                onClick={() => handleExpand(doc.id)}
              >
                <div className="flex items-start gap-3">
                  <IconComp
                    size={28}
                    className="text-primary shrink-0 mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium truncate">
                      {doc.filename}
                    </h3>
                    <div className="flex flex-wrap items-center gap-1.5 mt-1">
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">
                        {doc.domain}
                      </span>
                      <span className="text-[10px] text-base-content/40">
                        {doc.memory_count} memories
                      </span>
                      <DurabilityBadge durability={doc.durability} />
                      {doc.pinned && (
                        <span className="text-[10px] text-amber-400">
                          <PushPin size={10} weight="fill" />
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-base-content/30 mt-1">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div
                    className="flex gap-1 shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      className="btn btn-ghost btn-xs"
                      onClick={() => handlePin(doc)}
                      title={doc.pinned ? "Unpin" : "Pin"}
                    >
                      {doc.pinned ? (
                        <PushPinSlash size={14} />
                      ) : (
                        <PushPin size={14} />
                      )}
                    </button>
                    <button
                      className="btn btn-ghost btn-xs text-error"
                      onClick={() => setDeleteTarget(doc)}
                      title="Delete"
                    >
                      <Trash size={14} />
                    </button>
                  </div>
                </div>

                {/* Expanded detail */}
                {isExpanded && detail && detail.id === doc.id && (
                  <div className="mt-4 border-t border-base-content/5 pt-3">
                    <p className="text-xs text-base-content/50 mb-2">
                      {detail.child_memory_ids.length} child memories
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {detail.child_memory_ids.slice(0, 20).map((cid) => (
                        <span
                          key={cid}
                          className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-base-300 text-base-content/40"
                        >
                          {cid.slice(0, 8)}...
                        </span>
                      ))}
                      {detail.child_memory_ids.length > 20 && (
                        <span className="text-[9px] text-base-content/30">
                          +{detail.child_memory_ids.length - 20} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
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
        confirmClass="btn-error"
        onConfirm={() => deleteTarget && handleDelete(deleteTarget)}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
