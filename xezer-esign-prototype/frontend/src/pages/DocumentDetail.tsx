import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { Icon } from "../components/Icon";
import { SignModal } from "../components/SignModal";
import { Timeline } from "../components/Timeline";
import { AssetCode, Field, Modal, Notice, Panel, SignatureProgress, StatusChip } from "../components/ui";
import { useApp } from "../context";
import { CATEGORY_LABEL, fmtDate, fmtDateTime, groupedHash, shortHash } from "../format";
import { navigate } from "../router";
import type { DocumentDetail } from "../types";

type ModalKind = "sign" | "reopen" | "cancel" | "release" | null;

export function DocumentDetailPage({ id }: { id: number }) {
  const { user, switchUser, toast } = useApp();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalKind>(null);
  const [busy, setBusy] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    api
      .document(id)
      .then(setDoc)
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Could not load document."));
  }, [id]);

  const closeModal = useCallback(() => {
    setModal(null);
    setActionError(null);
  }, []);

  async function run(action: () => Promise<DocumentDetail>, success: (d: DocumentDetail) => string, after?: (d: DocumentDetail) => void) {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await action();
      setDoc(updated);
      setModal(null);
      toast(success(updated));
      after?.(updated);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "The action failed.";
      if (modal) setActionError(msg);
      else toast(msg, "error");
    } finally {
      setBusy(false);
    }
  }

  if (loadError) return <div className="page"><Notice tone="danger" icon="alert">{loadError}</Notice></div>;
  if (!doc) return <div className="page"><div className="empty">Loading…</div></div>;

  const a = doc.actions;
  const locked = doc.status !== "DRAFT";
  const readOnly = doc.status === "RELEASED" || doc.status === "CANCELLED";
  const next = a.next_signer;

  return (
    <div className="page">
      <a className="back-link" href="#/">
        <Icon name="back" size={14} /> Documents
      </a>

      {/* ------------------------------------------------------------ header */}
      <section className="panel doc-header">
        <div className="doc-header-main">
          <div className="doc-title-row">
            <span className="doc-no doc-no-xl">{doc.document_number}</span>
            <StatusChip status={doc.status} />
            {doc.revision > 1 && <span className="tag">Revision {doc.revision}</span>}
            {readOnly && (
              <span className="tag tag-lock">
                <Icon name="lock" size={12} /> Read-only
              </span>
            )}
          </div>
          <div className="doc-type">
            {doc.type_label} · <span>{doc.type_label_az}</span>
          </div>
          <div className="doc-meta">
            Created {fmtDateTime(doc.created_at)} by {doc.created_by.full_name}
            {doc.submitted_at && <> · Sent for signatures {fmtDateTime(doc.submitted_at)}</>}
          </div>
        </div>
        <div className="doc-header-actions">
          <button className="btn" onClick={() => navigate(`/documents/${doc.id}/print`)}>
            <Icon name="print" /> PDF / Print
          </button>
          {a.can_cancel && (
            <button className="btn btn-ghost-danger" onClick={() => setModal("cancel")}>
              <Icon name="ban" /> Cancel document
            </button>
          )}
          {a.can_edit && (
            <button className="btn" onClick={() => navigate(`/documents/${doc.id}/edit`)}>
              <Icon name="edit" /> Edit
            </button>
          )}
          {a.can_reopen && (
            <button className={a.reopen_invalidates ? "btn btn-warn" : "btn"} onClick={() => setModal("reopen")}>
              <Icon name="edit" /> {a.reopen_invalidates ? "Edit document and invalidate signatures" : "Edit document"}
            </button>
          )}
          {a.can_submit && (
            <button
              className="btn btn-primary"
              disabled={busy}
              onClick={() =>
                run(
                  () => api.submit(doc.id),
                  (d) => `Sent for signatures — waiting for ${d.actions.next_signer?.full_name}`,
                )
              }
            >
              <Icon name="send" /> Send for signatures
            </button>
          )}
        </div>
      </section>

      <StatusBanner doc={doc} />

      <div className="detail-grid">
        {/* ------------------------------------------------------------ left column */}
        <div className="detail-main">
          <Panel title="Recipient & handover details" aside={locked && !readOnly ? <span className="muted"><Icon name="lock" size={12} /> Content locked for signing</span> : undefined}>
            <div className="fields">
              <Field label="Recipient">
                <strong>{doc.recipient.full_name}</strong>
                <span className="muted"> · {doc.recipient.title}</span>
              </Field>
              <Field label="Department">
                {doc.department.code} · {doc.department.name}
              </Field>
              <Field label="Issue date">{fmtDate(doc.issue_date)}</Field>
              <Field label="Expected return date">{fmtDate(doc.expected_return_date)}</Field>
              <Field label="Purpose" wide>
                {doc.purpose}
              </Field>
              <Field label="Notes" wide>
                {doc.notes || <span className="muted">—</span>}
              </Field>
            </div>
          </Panel>

          <Panel
            title={
              <>
                Equipment <span className="count-badge neutral">{doc.items.length} items</span>
              </>
            }
            flush
          >
            <table className="table equipment-table">
              <thead>
                <tr>
                  <th className="col-line">#</th>
                  <th>Asset ID</th>
                  <th>Description</th>
                  <th>Category</th>
                  <th>Power</th>
                </tr>
              </thead>
              <tbody>
                {doc.items.map((i) => (
                  <tr key={i.asset_code}>
                    <td className="col-line">{i.line_no}</td>
                    <td>
                      <AssetCode code={i.asset_code} large />
                    </td>
                    <td>{i.category === "LAMP" ? `${i.type_name} lamp` : i.type_name}</td>
                    <td className="muted">{CATEGORY_LABEL[i.category]}</td>
                    <td>{i.power}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>

          <FingerprintPanel doc={doc} />
        </div>

        {/* ------------------------------------------------------------ right column */}
        <div className="detail-side">
          <Panel
            title="İmzalar"
            aside={
              <span className={`sig-headline${doc.signed_count === doc.required_count ? " done" : ""}`}>
                {doc.signed_count} / {doc.required_count} tamamlandı
              </span>
            }
          >
            <SignatureProgress signed={doc.signed_count} total={doc.required_count} wide />
            <ol className="sig-steps">
              {doc.signers.map((s) => {
                const isNext = s.state === "NEXT" && doc.status === "WAITING_FOR_SIGNATURES";
                return (
                  <li key={s.signing_order} className={`sig-step state-${s.state.toLowerCase()}${isNext ? " is-next" : ""}`}>
                    <span className="step-icon">
                      {s.state === "SIGNED" ? <Icon name="check" size={14} /> : s.signing_order}
                    </span>
                    <div className="step-body">
                      <div className="step-role">
                        {s.role_label}
                        {s.user.id === user.id && <span className="you-tag">You</span>}
                      </div>
                      <div className="step-name">
                        {s.user.full_name} <span className="muted">· {s.user.title}</span>
                      </div>
                      {s.signature ? (
                        <div className="step-meta">
                          {fmtDateTime(s.signature.signed_at)} · PIN · <span className="mono">{shortHash(s.signature.document_hash)}</span>
                        </div>
                      ) : (
                        <div className="step-wait">
                          {doc.status === "DRAFT" || doc.status === "CANCELLED"
                            ? "Not requested"
                            : isNext
                              ? "İmza gözlənilir — next to sign"
                              : "İmza gözlənilir"}
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>

            <SignArea
              doc={doc}
              onSign={() => setModal("sign")}
              onSwitch={next && next.user_id !== user.id ? () => switchUser(next.user_id) : undefined}
            />
          </Panel>

          {doc.invalidated_signatures.length > 0 && (
            <Panel title="Invalidated signatures" aside={<span className="muted">earlier versions</span>}>
              <ul className="invalidated-list">
                {doc.invalidated_signatures.map((s) => (
                  <li key={s.id}>
                    <div>
                      <s>{s.signer_name}</s> <span className="muted">· {s.signer_role_label} · rev. {s.document_revision}</span>
                    </div>
                    <div className="muted tiny">
                      Signed {fmtDateTime(s.signed_at)} · <span className="mono">{shortHash(s.document_hash)}</span> · invalidated{" "}
                      {fmtDateTime(s.invalidated_at)}
                    </div>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="Equipment release" aside={<span className="muted">Avadanlığın təhvili</span>}>
            <ReleaseArea doc={doc} busy={busy} onRelease={() => setModal("release")} />
          </Panel>

          <Panel title="Audit timeline" aside={<span className="muted">{doc.events.length} events</span>}>
            <Timeline events={doc.events} />
          </Panel>
        </div>
      </div>

      {/* ------------------------------------------------------------ modals */}
      {modal === "sign" && (
        <SignModal
          doc={doc}
          onClose={closeModal}
          onSigned={(d) => {
            setDoc(d);
            setModal(null);
            toast(
              d.status === "SIGNED"
                ? `Signed — ${d.signed_count} / ${d.required_count} complete. Equipment can now be released.`
                : `Signed — ${d.signed_count} / ${d.required_count} signatures complete`,
            );
          }}
        />
      )}

      {modal === "reopen" && (
        <Modal
          title={a.reopen_invalidates ? "Edit document and invalidate signatures" : "Return document to draft"}
          onClose={closeModal}
          width={520}
          footer={
            <>
              <button className="btn" onClick={closeModal}>Keep signatures</button>
              <button
                className={a.reopen_invalidates ? "btn btn-danger" : "btn btn-primary"}
                disabled={busy}
                onClick={() =>
                  run(
                    () => api.reopen(doc.id),
                    () => (a.reopen_invalidates ? `${a.reopen_invalidates} signature(s) invalidated — document is a draft again` : "Document returned to draft"),
                    (d) => navigate(`/documents/${d.id}/edit`),
                  )
                }
              >
                {a.reopen_invalidates ? "Invalidate signatures and edit" : "Return to draft and edit"}
              </button>
            </>
          }
        >
          {a.reopen_invalidates ? (
            <>
              <Notice tone="warn" icon="alert">
                <strong>
                  {a.reopen_invalidates} existing signature{a.reopen_invalidates > 1 ? "s" : ""} will be invalidated.
                </strong>{" "}
                Signatures cannot be carried over to changed content.
              </Notice>
              <ul className="reopen-list">
                {doc.signers
                  .filter((s) => s.signature)
                  .map((s) => (
                    <li key={s.signing_order}>
                      <Icon name="x" size={13} /> {s.user.full_name} · {s.role_label} · signed {fmtDateTime(s.signature!.signed_at)}
                    </li>
                  ))}
              </ul>
              <ol className="reopen-steps">
                <li>The document returns to <b>Draft</b> and can be edited.</li>
                <li>Sending it again creates a <b>new fingerprint</b> (current: {shortHash(doc.payload_hash)}).</li>
                <li>All {doc.required_count} signers must sign again, in order.</li>
                <li>Invalidated signatures stay visible in the history and audit timeline.</li>
              </ol>
            </>
          ) : (
            <p>
              Nobody has signed yet. The document returns to Draft for editing; sending it again creates a new
              fingerprint.
            </p>
          )}
          {actionError && <div className="form-error"><Icon name="alert" size={15} /> {actionError}</div>}
        </Modal>
      )}

      {modal === "cancel" && (
        <Modal
          title={`Cancel ${doc.document_number}?`}
          onClose={closeModal}
          footer={
            <>
              <button className="btn" onClick={closeModal}>Back</button>
              <button
                className="btn btn-danger"
                disabled={busy || !cancelReason.trim()}
                onClick={() => run(() => api.cancel(doc.id, cancelReason), (d) => `${d.document_number} cancelled`)}
              >
                Cancel document
              </button>
            </>
          }
        >
          <p>The document becomes read-only and its equipment is freed for other handovers. This cannot be undone.</p>
          <label className="form-field">
            <span>Reason *</span>
            <textarea rows={3} value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} autoFocus />
          </label>
          {actionError && <div className="form-error"><Icon name="alert" size={15} /> {actionError}</div>}
        </Modal>
      )}

      {modal === "release" && (
        <Modal
          title="Avadanlığı təhvil ver"
          onClose={closeModal}
          footer={
            <>
              <button className="btn" onClick={closeModal}>Back</button>
              <button
                className="btn btn-success"
                disabled={busy}
                onClick={() =>
                  run(() => api.release(doc.id), (d) => `Equipment released to ${d.recipient.full_name} — ${d.document_number} is now read-only`)
                }
              >
                <Icon name="release" /> Confirm release
              </button>
            </>
          }
        >
          <p>
            Release the following equipment to <strong>{doc.recipient.full_name}</strong> ({doc.department.code}):
          </p>
          <div className="asset-list release-assets">
            {doc.items.map((i) => (
              <AssetCode key={i.asset_code} code={i.asset_code} large />
            ))}
          </div>
          <p className="muted">
            The release is recorded under your name with the current time. The document then becomes read-only.
          </p>
          {actionError && <div className="form-error"><Icon name="alert" size={15} /> {actionError}</div>}
        </Modal>
      )}
    </div>
  );
}

function StatusBanner({ doc }: { doc: DocumentDetail }) {
  const next = doc.actions.next_signer;
  switch (doc.status) {
    case "DRAFT":
      return (
        <Notice tone="neutral" icon="edit">
          <strong>Draft.</strong> Content can still be edited. Sending for signatures locks the content and calculates
          its SHA-256 fingerprint.
          {doc.invalidated_signatures.length > 0 && " Earlier signatures were invalidated — everyone must sign again."}
        </Notice>
      );
    case "WAITING_FOR_SIGNATURES":
      return (
        <Notice tone="warn" icon="pen">
          <strong>
            Waiting for {next?.full_name} ({next?.role_label}).
          </strong>{" "}
          {doc.signed_count} of {doc.required_count} signatures complete. Content is locked; equipment release is
          blocked until all signatures are in.
        </Notice>
      );
    case "SIGNED":
      return (
        <Notice tone="info" icon="shield">
          <strong>All {doc.required_count} signatures complete.</strong> The Warehouse Operator can now release the
          equipment.
        </Notice>
      );
    case "RELEASED":
      return (
        <Notice tone="ok" icon="lock">
          <strong>Equipment released {fmtDateTime(doc.released_at)}</strong> by {doc.released_by?.full_name}. This
          signed document is read-only.
        </Notice>
      );
    case "CANCELLED":
      return (
        <Notice tone="danger" icon="ban">
          <strong>Cancelled {fmtDateTime(doc.cancelled_at)}</strong> by {doc.cancelled_by?.full_name}
          {doc.cancel_reason && <> — {doc.cancel_reason}</>}
        </Notice>
      );
  }
}

function SignArea({ doc, onSign, onSwitch }: { doc: DocumentDetail; onSign: () => void; onSwitch?: () => void }) {
  const { user } = useApp();
  const a = doc.actions;
  const mine = doc.signers.find((s) => s.user.id === user.id);
  const waiting = doc.status === "WAITING_FOR_SIGNATURES";

  return (
    <div className="sign-area">
      {a.can_sign && (
        <button className="btn btn-primary btn-block btn-lg" onClick={onSign}>
          <Icon name="pen" /> İmzala
          <span className="btn-sub">as {mine?.role_label}</span>
        </button>
      )}
      {!a.can_sign && waiting && a.is_signer && a.my_step_state !== "SIGNED" && (
        <>
          <button className="btn btn-block btn-lg" disabled>
            <Icon name="lock" /> İmzala
          </button>
          <div className="blocked-reason">
            <Icon name="lock" size={13} /> {a.sign_blocked_reason}
          </div>
        </>
      )}
      {mine?.signature && (
        <div className="signed-note">
          <Icon name="check" size={14} /> You signed on {fmtDateTime(mine.signature.signed_at)}.
        </div>
      )}
      {waiting && !a.is_signer && (
        <div className="blocked-reason">You are not a required signer on this document.</div>
      )}
      {waiting && onSwitch && a.next_signer && (
        <button className="demo-switch" onClick={onSwitch}>
          <Icon name="swap" size={13} /> Demo: switch to {a.next_signer.full_name} to sign
        </button>
      )}
    </div>
  );
}

function ReleaseArea({ doc, busy, onRelease }: { doc: DocumentDetail; busy: boolean; onRelease: () => void }) {
  const a = doc.actions;
  if (doc.status === "RELEASED") {
    return (
      <div className="release-done">
        <Icon name="check" size={16} />
        <div>
          <strong>Released {fmtDateTime(doc.released_at)}</strong>
          <div className="muted">
            by {doc.released_by?.full_name} · {doc.items.map((i) => i.asset_code).join(", ")} issued to{" "}
            {doc.recipient.full_name}
          </div>
        </div>
      </div>
    );
  }
  if (doc.status === "CANCELLED") return <div className="muted">Document cancelled — no equipment was released.</div>;

  const allSigned = doc.signed_count === doc.required_count && doc.status === "SIGNED";
  return (
    <div className="release-area">
      <ul className="gate-list">
        <li className={allSigned ? "ok" : ""}>
          <Icon name={allSigned ? "check" : "lock"} size={13} /> All required signatures ({doc.signed_count} / {doc.required_count})
        </li>
        <li className={doc.integrity === "VERIFIED" ? "ok" : ""}>
          <Icon name={doc.integrity === "VERIFIED" ? "check" : "lock"} size={13} /> Content matches the signed fingerprint
        </li>
        <li className={allSigned ? "" : "dim"}>
          <Icon name="user" size={13} /> Warehouse Operator confirms hand-over
        </li>
      </ul>
      <button className="btn btn-success btn-block btn-lg" disabled={!a.can_release || busy} onClick={onRelease}>
        <Icon name={a.can_release ? "release" : "lock"} /> Avadanlığı təhvil ver
      </button>
      {!a.can_release && a.release_blocked_reason && (
        <div className="blocked-reason">
          <Icon name="lock" size={13} /> {a.release_blocked_reason}
        </div>
      )}
    </div>
  );
}

function FingerprintPanel({ doc }: { doc: DocumentDetail }) {
  if (!doc.payload_hash) {
    return (
      <Panel title="Document fingerprint">
        <div className="muted">
          No fingerprint yet. It is calculated (SHA-256 over a canonical snapshot of all document content) when the
          document is sent for signatures.
        </div>
      </Panel>
    );
  }
  let pretty = doc.payload_snapshot ?? "";
  try {
    pretty = JSON.stringify(JSON.parse(pretty), null, 2);
  } catch {
    /* show raw */
  }
  return (
    <Panel
      title="Document fingerprint"
      aside={
        doc.integrity === "VERIFIED" ? (
          <span className="chip chip-green">
            <Icon name="shield" size={12} /> Verified · content unchanged
          </span>
        ) : (
          <span className="chip chip-red">
            <Icon name="alert" size={12} /> Content does not match fingerprint
          </span>
        )
      }
    >
      <div className="fp-row">
        <Icon name="fingerprint" size={22} className="fp-icon" />
        <div>
          <div className="fp-short">{shortHash(doc.payload_hash)}</div>
          <div className="fp-full">SHA-256 · {groupedHash(doc.payload_hash)}</div>
        </div>
      </div>
      <p className="muted small-text">
        Calculated from a canonical snapshot of the document number, recipient, department, equipment, purpose,
        dates, notes and required signers. Every signature records this exact value.
      </p>
      <details className="snapshot">
        <summary>Show signed snapshot (canonical data)</summary>
        <pre>{pretty}</pre>
      </details>
    </Panel>
  );
}
