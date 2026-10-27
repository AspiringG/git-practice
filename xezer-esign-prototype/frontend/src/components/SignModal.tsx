import { useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { useApp } from "../context";
import { fmtDate, groupedHash, shortHash } from "../format";
import type { DocumentDetail } from "../types";
import { Icon } from "./Icon";
import { AssetCode, Avatar, Modal } from "./ui";

export function SignModal({
  doc,
  onClose,
  onSigned,
}: {
  doc: DocumentDetail;
  onClose: () => void;
  onSigned: (doc: DocumentDetail) => void;
}) {
  const { user } = useApp();
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const step = doc.signers.find((s) => s.user.id === user.id)!;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!pin || busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.sign(doc.id, pin, doc.payload_hash!);
      setPin("");
      onSigned(updated);
    } catch (err) {
      setPin("");
      setError(err instanceof ApiError ? err.message : "Signing failed.");
      setTimeout(() => inputRef.current?.focus(), 0);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Sign document" onClose={onClose} width={500}>
      <form onSubmit={submit} className="sign-form" autoComplete="off">
        <div className="sign-doc">
          <span className="doc-no doc-no-lg">{doc.document_number}</span>
          <span className="muted">
            {doc.type_label} · {doc.type_label_az}
          </span>
        </div>

        <div className="sign-section">
          <div className="sign-label">You are signing as</div>
          <div className="sign-who">
            <Avatar name={user.full_name} />
            <div>
              <strong>{user.full_name}</strong>
              <small>
                {user.title} · signing as <b>{step.role_label}</b> (step {step.signing_order} of {doc.required_count})
              </small>
            </div>
          </div>
        </div>

        <div className="sign-summary">
          <div>
            <span className="sign-label">Recipient</span>
            {doc.recipient.full_name} · {doc.department.code}
          </div>
          <div>
            <span className="sign-label">Period</span>
            {fmtDate(doc.issue_date)} → {fmtDate(doc.expected_return_date)}
          </div>
          <div className="sign-summary-wide">
            <span className="sign-label">Equipment ({doc.items.length})</span>
            <span className="asset-list">
              {doc.items.map((i) => (
                <AssetCode key={i.asset_code} code={i.asset_code} />
              ))}
            </span>
          </div>
        </div>

        <div className="sign-fingerprint">
          <div className="sign-label">
            <Icon name="fingerprint" size={14} /> Document fingerprint (SHA-256)
          </div>
          <div className="fp-short">{shortHash(doc.payload_hash)}</div>
          <div className="fp-full">{groupedHash(doc.payload_hash!)}</div>
        </div>

        <p className="sign-statement">
          By entering your signing PIN you confirm that you have reviewed this handover and agree with its content.
          Your signature is bound to the fingerprint above — any later change to the document invalidates it.
        </p>

        <label className="pin-field">
          <span>Signing PIN</span>
          <input
            ref={inputRef}
            type="password"
            inputMode="numeric"
            autoComplete="off"
            name="signing-pin"
            maxLength={12}
            autoFocus
            value={pin}
            onChange={(e) => {
              setPin(e.target.value);
              setError(null);
            }}
            aria-invalid={!!error}
            placeholder="••••"
          />
        </label>
        {error && (
          <div className="form-error" role="alert">
            <Icon name="alert" size={15} /> {error}
          </div>
        )}

        <div className="modal-actions">
          <span className="muted tiny">Internal signature · not a qualified electronic signature</span>
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={!pin || busy}>
            <Icon name="pen" /> {busy ? "Signing…" : "İmzala"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
