import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import type { DocumentItem } from "../api";

export function selectionLabel(selected: string[], documents: DocumentItem[]): string {
  if (selected.length === 0) return "Choose documents";
  if (selected.length === documents.length && documents.length > 1) return `All ${documents.length} documents`;
  if (selected.length === 1) return documents.find((d) => d.id === selected[0])?.filename ?? "1 document";
  return `${selected.length} documents`;
}

export function DocumentChecklist({
  documents,
  selected,
  onChange,
}: {
  documents: DocumentItem[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const chosen = new Set(selected);
  const toggle = (id: string) =>
    onChange(chosen.has(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  const allChosen = documents.length > 0 && documents.every((d) => chosen.has(d.id));
  return (
    <div className="doc-checklist">
      <div className="doc-checklist-head">
        <span className="muted">
          {selected.length} of {documents.length} selected
        </span>
        <button type="button" className="link-btn" onClick={() => onChange(allChosen ? [] : documents.map((d) => d.id))}>
          {allChosen ? "Clear all" : "Select all"}
        </button>
      </div>
      {documents.map((d) => (
        <label key={d.id} className={`doc-option${chosen.has(d.id) ? " checked" : ""}`}>
          <input type="checkbox" checked={chosen.has(d.id)} onChange={() => toggle(d.id)} />
          <span className="doc-option-name" title={d.filename}>
            {d.filename}
          </span>
        </label>
      ))}
    </div>
  );
}

export function DocumentPicker({
  documents,
  selected,
  onChange,
  disabled = false,
}: {
  documents: DocumentItem[];
  selected: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="picker" ref={ref}>
      <button
        type="button"
        className={`picker-button${selected.length === 0 ? " empty" : ""}`}
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        aria-expanded={open}
      >
        <span className="picker-label">Documents</span>
        <span className="picker-value">{selectionLabel(selected, documents)}</span>
      </button>
      {open && (
        <div className="picker-panel" role="dialog" aria-label="Choose documents">
          {documents.length === 0 ? (
            <p className="muted">
              No documents yet. <Link to="/documents">Upload one</Link> to start.
            </p>
          ) : (
            <DocumentChecklist documents={documents} selected={selected} onChange={onChange} />
          )}
        </div>
      )}
    </div>
  );
}

export function WebToggle({
  on,
  onChange,
  available,
  disabled = false,
}: {
  on: boolean;
  onChange: (on: boolean) => void;
  available: boolean;
  disabled?: boolean;
}) {
  const hint = !available
    ? "Web search isn't set up on this server"
    : on
      ? "Your documents first, then the web when they don't have the answer"
      : "Answers come only from the selected documents";
  return (
    <label className={`switch${on ? " on" : ""}${!available ? " unavailable" : ""}`} title={hint}>
      <input
        type="checkbox"
        role="switch"
        checked={on && available}
        disabled={disabled || !available}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="switch-track" aria-hidden="true">
        <span className="switch-thumb" />
      </span>
      <span className="switch-text">
        <b>Web search</b>
        <span>{on && available ? "On" : "Off"}</span>
      </span>
    </label>
  );
}
