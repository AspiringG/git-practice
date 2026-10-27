import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { AssetCode, SignatureProgress, StatusChip } from "../components/ui";
import { useApp } from "../context";
import { fmtDate, fmtDateTime, STATUS_META, STATUS_ORDER } from "../format";
import { navigate } from "../router";
import type { DocumentSummary, Status } from "../types";

function progressNote(d: DocumentSummary) {
  switch (d.status) {
    case "DRAFT":
      return "Not yet sent for signatures";
    case "WAITING_FOR_SIGNATURES":
      return `Waiting for ${d.next_signer_role}`;
    case "SIGNED":
      return "All signed · ready for release";
    case "RELEASED":
      return `Released ${fmtDateTime(d.released_at)}`;
    case "CANCELLED":
      return "Cancelled";
  }
}

export function Dashboard() {
  const { user } = useApp();
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [filter, setFilter] = useState<Status | "ALL">("ALL");
  const [query, setQuery] = useState("");
  const isOperator = user.role === "WAREHOUSE_OPERATOR";

  useEffect(() => {
    api.documents().then(setDocs).catch(() => setDocs([]));
  }, []);

  const counts = useMemo(() => {
    const c = Object.fromEntries(STATUS_ORDER.map((s) => [s, 0])) as Record<Status, number>;
    docs?.forEach((d) => c[d.status]++);
    return c;
  }, [docs]);

  const actionItems = useMemo(() => {
    if (!docs) return [];
    return docs
      .filter((d) => d.awaiting_me || (isOperator && (d.status === "SIGNED" || d.status === "DRAFT")))
      .map((d) => ({
        doc: d,
        label: d.awaiting_me
          ? "Your signature is required"
          : d.status === "SIGNED"
            ? "3 / 3 signed — release the equipment"
            : "Draft — review and send for signatures",
        cta: d.awaiting_me ? "Open & sign" : d.status === "SIGNED" ? "Open & release" : "Open draft",
      }));
  }, [docs, isOperator]);

  const visible = useMemo(() => {
    if (!docs) return [];
    const q = query.trim().toLowerCase();
    return docs.filter(
      (d) =>
        (filter === "ALL" || d.status === filter) &&
        (!q ||
          d.document_number.toLowerCase().includes(q) ||
          d.recipient_name.toLowerCase().includes(q) ||
          d.purpose.toLowerCase().includes(q) ||
          d.asset_codes.some((a) => a.toLowerCase().includes(q))),
    );
  }, [docs, filter, query]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="eyebrow">Anbar · Sənəd dövriyyəsi</div>
          <h1>Təhvil-təslim aktları</h1>
          <p className="page-sub">Warehouse equipment handovers with internal electronic signatures</p>
        </div>
        <div className="page-actions">
          <button
            className="btn btn-primary"
            disabled={!isOperator}
            title={isOperator ? undefined : "Only the Warehouse Operator creates handover documents"}
            onClick={() => navigate("/documents/new")}
          >
            <Icon name="plus" /> New handover
          </button>
        </div>
      </div>

      <div className="status-tiles">
        {STATUS_ORDER.map((s) => (
          <button
            key={s}
            className={`status-tile tone-${STATUS_META[s].tone}${filter === s ? " active" : ""}`}
            onClick={() => setFilter(filter === s ? "ALL" : s)}
          >
            <span className="tile-count">{docs ? counts[s] : "–"}</span>
            <span className="tile-label">
              {s === "RELEASED" ? "Completed / Released" : STATUS_META[s].label}
              <small>{STATUS_META[s].az}</small>
            </span>
          </button>
        ))}
      </div>

      {actionItems.length > 0 && (
        <section className="panel action-panel">
          <header className="panel-head">
            <h2>
              Requires your action <span className="count-badge">{actionItems.length}</span>
            </h2>
            <span className="muted">Signed in as {user.full_name} · {user.title}</span>
          </header>
          <div className="action-list">
            {actionItems.map(({ doc, label, cta }) => (
              <button key={doc.id} className="action-row" onClick={() => navigate(`/documents/${doc.id}`)}>
                <span className="doc-no">{doc.document_number}</span>
                <span className="action-label">{label}</span>
                <span className="muted">
                  {doc.recipient_name} · {doc.department_code} · {doc.asset_codes.length} items
                </span>
                <SignatureProgress signed={doc.signed_count} total={doc.required_count} />
                <span className="action-cta">
                  {cta} <Icon name="back" size={13} className="flip" />
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="panel">
        <header className="panel-head">
          <h2>
            {filter === "ALL" ? "All documents" : STATUS_META[filter].label}
            <span className="count-badge neutral">{visible.length}</span>
          </h2>
          <div className="panel-aside">
            {filter !== "ALL" && (
              <button className="btn btn-ghost btn-sm" onClick={() => setFilter("ALL")}>
                Clear filter
              </button>
            )}
            <label className="search">
              <Icon name="search" size={14} />
              <input
                placeholder="Search number, recipient, asset ID…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
          </div>
        </header>
        <div className="table-wrap">
          <table className="table doc-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Recipient</th>
                <th>Equipment</th>
                <th>Signatures</th>
                <th>Status</th>
                <th className="col-created">Created</th>
              </tr>
            </thead>
            <tbody>
              {!docs && (
                <tr>
                  <td colSpan={6} className="empty">
                    Loading…
                  </td>
                </tr>
              )}
              {docs && visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty">
                    No documents in this category.
                  </td>
                </tr>
              )}
              {visible.map((d) => (
                <tr key={d.id} className={`clickable${d.awaiting_me ? " row-highlight" : ""}`} onClick={() => navigate(`/documents/${d.id}`)}>
                  <td>
                    <div className="doc-no">{d.document_number}</div>
                    <div className="cell-sub" title={d.purpose}>
                      {d.purpose}
                    </div>
                  </td>
                  <td>
                    <div className="cell-main">{d.recipient_name}</div>
                    <div className="cell-sub">
                      {d.department_code} · {d.department_name}
                    </div>
                  </td>
                  <td>
                    <div className="asset-list">
                      {d.asset_codes.slice(0, 3).map((a) => (
                        <AssetCode key={a} code={a} />
                      ))}
                      {d.asset_codes.length > 3 && <span className="muted">+{d.asset_codes.length - 3}</span>}
                    </div>
                    <div className="cell-sub">
                      {d.asset_codes.length} equipment item{d.asset_codes.length === 1 ? "" : "s"} · issue {fmtDate(d.issue_date)}
                    </div>
                  </td>
                  <td>
                    <SignatureProgress signed={d.signed_count} total={d.required_count} />
                    <div className={`cell-sub${d.awaiting_me ? " text-blue" : ""}`}>
                      {d.awaiting_me ? "Waiting for you" : progressNote(d)}
                    </div>
                  </td>
                  <td>
                    <StatusChip status={d.status} />
                  </td>
                  <td className="col-created nowrap">{fmtDateTime(d.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
