import { useEffect, type ReactNode } from "react";
import { STATUS_META, initials } from "../format";
import type { Status } from "../types";
import { Icon } from "./Icon";

export function StatusChip({ status, az = false }: { status: Status; az?: boolean }) {
  const meta = STATUS_META[status];
  return (
    <span className={`chip chip-${meta.tone}`}>
      <span className="chip-dot" />
      {az ? meta.az : meta.label}
    </span>
  );
}

export function AssetCode({ code, large = false }: { code: string; large?: boolean }) {
  return <span className={`asset-code${large ? " asset-code-lg" : ""}`}>{code}</span>;
}

export function SignatureProgress({ signed, total, wide = false }: { signed: number; total: number; wide?: boolean }) {
  return (
    <span className={`sig-progress${wide ? " sig-progress-wide" : ""}`} aria-label={`${signed} of ${total} signatures`}>
      <span className="sig-segments">
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={`sig-seg${i < signed ? " on" : ""}${signed === total ? " done" : ""}`} />
        ))}
      </span>
      <span className="sig-count">
        {signed} / {total}
      </span>
    </span>
  );
}

export function Avatar({ name, small = false }: { name: string; small?: boolean }) {
  return <span className={`avatar${small ? " avatar-sm" : ""}`}>{initials(name)}</span>;
}

export function Panel({
  title,
  aside,
  children,
  className = "",
  flush = false,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
}) {
  return (
    <section className={`panel ${className}`}>
      {title !== undefined && (
        <header className="panel-head">
          <h2>{title}</h2>
          {aside && <div className="panel-aside">{aside}</div>}
        </header>
      )}
      <div className={flush ? "panel-body flush" : "panel-body"}>{children}</div>
    </section>
  );
}

export function Modal({
  title,
  onClose,
  children,
  footer,
  width = 460,
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ width }} role="dialog" aria-modal="true">
        <header className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <Icon name="x" />
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  );
}

export function Field({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`field${wide ? " field-wide" : ""}`}>
      <div className="field-label">{label}</div>
      <div className="field-value">{children}</div>
    </div>
  );
}

export function Notice({ tone, icon, children }: { tone: "info" | "warn" | "ok" | "danger" | "neutral"; icon?: string; children: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`}>
      {icon && <Icon name={icon} size={16} className="notice-icon" />}
      <div>{children}</div>
    </div>
  );
}
