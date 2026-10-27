import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { CATEGORY_LABEL, fmtDate, fmtDateTime, groupedHash, shortHash, STATUS_META } from "../format";
import { navigate } from "../router";
import type { DocumentDetail } from "../types";

export function PrintView({ id }: { id: number }) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [printedAt] = useState(() => new Date().toISOString());

  useEffect(() => {
    api.document(id).then(setDoc).catch(() => {});
  }, [id]);

  if (!doc) return <div className="boot-message">Loading…</div>;
  const final = doc.status === "SIGNED" || doc.status === "RELEASED";

  return (
    <div className="print-shell">
      <div className="print-toolbar no-print">
        <button className="btn" onClick={() => navigate(`/documents/${doc.id}`)}>
          <Icon name="back" size={14} /> Back to document
        </button>
        <span className="muted">Print preview · use “Save as PDF” in the print dialog to create a PDF</span>
        <button className="btn btn-primary" onClick={() => window.print()}>
          <Icon name="print" /> Print / Save as PDF
        </button>
      </div>

      <article className="print-page">
        <header className="pp-head">
          <div>
            <div className="pp-org">XEZER TV · Anbar</div>
            <h1>Təhvil-təslim aktı</h1>
            <div className="pp-sub">Warehouse equipment handover</div>
          </div>
          <div className="pp-number">
            <div className="pp-label">Document No.</div>
            <div className="pp-docno">{doc.document_number}</div>
            <div className={`pp-status pp-status-${STATUS_META[doc.status].tone}`}>
              {STATUS_META[doc.status].label} · {STATUS_META[doc.status].az}
            </div>
          </div>
        </header>

        {!final && (
          <div className="pp-watermark-note">
            {doc.status === "CANCELLED"
              ? "CANCELLED — this document is not valid for equipment release."
              : `NOT FINAL — ${doc.signed_count} of ${doc.required_count} required signatures.`}
          </div>
        )}

        <section className="pp-section">
          <table className="pp-fields">
            <tbody>
              <tr>
                <th>Recipient</th>
                <td>
                  {doc.recipient.full_name} — {doc.recipient.title}
                </td>
                <th>Department</th>
                <td>
                  {doc.department.code} · {doc.department.name}
                </td>
              </tr>
              <tr>
                <th>Issue date</th>
                <td>{fmtDate(doc.issue_date)}</td>
                <th>Expected return</th>
                <td>{fmtDate(doc.expected_return_date)}</td>
              </tr>
              <tr>
                <th>Purpose</th>
                <td colSpan={3}>{doc.purpose}</td>
              </tr>
              <tr>
                <th>Notes</th>
                <td colSpan={3}>{doc.notes || "—"}</td>
              </tr>
              <tr>
                <th>Prepared by</th>
                <td>
                  {doc.created_by.full_name} · {fmtDateTime(doc.created_at)}
                </td>
                <th>Revision</th>
                <td>{doc.revision || "—"}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section className="pp-section">
          <h2>Equipment · {doc.items.length} items</h2>
          <table className="pp-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Asset ID</th>
                <th>Description</th>
                <th>Category</th>
                <th>Power</th>
              </tr>
            </thead>
            <tbody>
              {doc.items.map((i) => (
                <tr key={i.asset_code}>
                  <td>{i.line_no}</td>
                  <td className="pp-asset">{i.asset_code}</td>
                  <td>{i.category === "LAMP" ? `${i.type_name} lamp` : i.type_name}</td>
                  <td>{CATEGORY_LABEL[i.category]}</td>
                  <td>{i.power}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="pp-section">
          <h2>
            Signatures · {doc.signed_count} / {doc.required_count}
          </h2>
          <table className="pp-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Role</th>
                <th>Signer</th>
                <th>Signed at</th>
                <th>Method</th>
                <th>Fingerprint signed</th>
              </tr>
            </thead>
            <tbody>
              {doc.signers.map((s) => (
                <tr key={s.signing_order}>
                  <td>{s.signing_order}</td>
                  <td>{s.role_label}</td>
                  <td>
                    {s.user.full_name}
                    <div className="pp-small">{s.user.title}</div>
                  </td>
                  <td>{s.signature ? fmtDateTime(s.signature.signed_at) : <em>Not signed</em>}</td>
                  <td>{s.signature ? "Internal PIN" : "—"}</td>
                  <td className="pp-mono">{s.signature ? shortHash(s.signature.document_hash) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="pp-section pp-grid">
          <div>
            <h2>Document fingerprint</h2>
            <div className="pp-mono pp-hash">{doc.payload_hash ? groupedHash(doc.payload_hash) : "Not yet generated"}</div>
            <div className="pp-small">
              SHA-256 of the canonical document snapshot. Integrity check at print time:{" "}
              <strong>{doc.integrity === "VERIFIED" ? "content matches fingerprint" : doc.integrity === "MISMATCH" ? "MISMATCH" : "n/a"}</strong>
            </div>
          </div>
          <div>
            <h2>Equipment release</h2>
            {doc.released_at ? (
              <div>
                Released {fmtDateTime(doc.released_at)} by {doc.released_by?.full_name} (Warehouse Operator)
              </div>
            ) : (
              <div>Not released</div>
            )}
          </div>
        </section>

        <footer className="pp-foot">
          <div>
            Prototype — internal electronic signature concept. Not a qualified electronic signature. Signatures are
            recorded electronically; no handwritten signature is reproduced.
          </div>
          <div>Printed {fmtDateTime(printedAt)} · Xezer ERP e-İmza prototype</div>
        </footer>
      </article>
    </div>
  );
}
