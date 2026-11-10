import { useRef, useState, type DragEvent } from "react";
import { api, formatDate, formatSize, type DocumentItem } from "../api";
import { useLibrary } from "../components/Library";
import { Button, ConfirmDialog, Skeleton, useToast } from "../components/ui";

const ACCEPTED = [".pdf", ".txt", ".md", ".markdown"];
const MAX_MB = 20;

interface UploadJob {
  key: string;
  name: string;
  progress: number;
  phase: "waiting" | "uploading" | "processing" | "done" | "error";
  error?: string;
}

let jobCounter = 0;

export default function DocumentsPage() {
  const { documents, setDocuments, refreshDocuments } = useLibrary();
  const notify = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [pendingDelete, setPendingDelete] = useState<DocumentItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const queue = useRef<Promise<void>>(Promise.resolve());

  const update = (key: string, patch: Partial<UploadJob>) =>
    setJobs((list) => list.map((j) => (j.key === key ? { ...j, ...patch } : j)));

  function addFiles(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      const key = `job-${++jobCounter}`;
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      let error: string | undefined;
      if (!ACCEPTED.includes(ext)) error = "Only PDF, TXT and Markdown files are supported.";
      else if (file.size > MAX_MB * 1024 * 1024) error = `Files can be up to ${MAX_MB} MB.`;
      else if (file.size === 0) error = "This file is empty.";
      setJobs((list) => [{ key, name: file.name, progress: 0, phase: error ? "error" : "waiting", error }, ...list]);
      if (error) continue;
      queue.current = queue.current.then(async () => {
        update(key, { phase: "uploading" });
        try {
          const doc = await api.uploadDocument(file, (p) =>
            update(key, p >= 1 ? { progress: 1, phase: "processing" } : { progress: p }),
          );
          update(key, { phase: "done", progress: 1 });
          setDocuments([doc, ...(documents ?? []).filter((d) => d.id !== doc.id)]);
          await refreshDocuments();
          window.setTimeout(() => setJobs((list) => list.filter((j) => j.key !== key)), 4000);
        } catch (err) {
          update(key, { phase: "error", error: (err as Error).message });
        }
      });
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.deleteDocument(pendingDelete.id);
      setDocuments((documents ?? []).filter((d) => d.id !== pendingDelete.id));
      notify(`${pendingDelete.filename} removed`);
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  }

  const stateLabel = (j: UploadJob) =>
    ({
      waiting: "Waiting",
      uploading: `Uploading ${Math.round(j.progress * 100)}%`,
      processing: "Reading the document",
      done: "Ready",
      error: "Couldn't add",
    })[j.phase];

  return (
    <div className="page">
      <div className="page-inner page-enter">
        <div className="page-head">
          <div>
            <h1>My documents</h1>
            <p className="lead">Everything you add here is private to you and used to answer your questions.</p>
          </div>
          <Button onClick={() => inputRef.current?.click()}>Upload files</Button>
        </div>

        <div
          className={`dropzone${over ? " over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        >
          <h3>Drop files here, or click to choose</h3>
          <p className="muted">PDF, TXT or Markdown, up to {MAX_MB} MB each.</p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED.join(",")}
            hidden
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {jobs.length > 0 && (
          <div className="uploads">
            {jobs.map((j) => (
              <div key={j.key} className="upload-item">
                <div className="top">
                  <span className="name">{j.name}</span>
                  <span className={`state${j.phase === "done" ? " ok" : j.phase === "error" ? " err" : ""}`}>
                    {stateLabel(j)}
                  </span>
                </div>
                {j.phase === "error" ? (
                  <div className="error-text" style={{ marginTop: 4 }}>
                    {j.error}
                  </div>
                ) : (
                  <div className={`bar${j.phase === "processing" || j.phase === "waiting" ? " indeterminate" : ""}`}>
                    <div style={{ width: j.phase === "processing" || j.phase === "waiting" ? undefined : `${j.progress * 100}%` }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="card doc-list">
          <div className="card-head">
            <h2>Library</h2>
            {documents && documents.length > 0 && (
              <span className="muted">
                {documents.length} document{documents.length === 1 ? "" : "s"}
              </span>
            )}
          </div>
          {documents === null ? (
            [0, 1, 2].map((i) => (
              <div key={i} className="doc-row">
                <div>
                  <Skeleton width="60%" height={16} />
                  <Skeleton width="30%" height={12} style={{ marginTop: 8 }} />
                </div>
              </div>
            ))
          ) : documents.length === 0 ? (
            <p className="muted">No documents yet. Upload a file above to get started.</p>
          ) : (
            documents.map((d) => (
              <div key={d.id} className="doc-row">
                <div style={{ minWidth: 0 }}>
                  <div className="name" title={d.filename}>
                    {d.filename}
                  </div>
                  <div className="sub">
                    {formatSize(d.size_bytes)} &middot; Added {formatDate(d.created_at)}
                  </div>
                </div>
                <span />
                <Button variant="ghost" size="sm" onClick={() => setPendingDelete(d)}>
                  Remove
                </Button>
              </div>
            ))
          )}
        </div>
      </div>

      {pendingDelete && (
        <ConfirmDialog
          title="Remove this document?"
          message={`${pendingDelete.filename} will be removed from your library. Answers will no longer use it.`}
          confirmLabel="Remove"
          busy={deleting}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}
