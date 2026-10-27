import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { Icon } from "../components/Icon";
import { AssetCode, Notice, Panel, StatusChip } from "../components/ui";
import { useApp } from "../context";
import { addDays, CATEGORY_LABEL, todayIso } from "../format";
import { navigate } from "../router";
import type { DocumentDetail, DocumentInput, Equipment, Recipient } from "../types";

export function DocumentForm({ id }: { id?: number }) {
  const { user, users, toast } = useApp();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [recipientId, setRecipientId] = useState<number | "">("");
  const [purpose, setPurpose] = useState("");
  const [issueDate, setIssueDate] = useState(todayIso());
  const [returnDate, setReturnDate] = useState(addDays(todayIso(), 7));
  const [notes, setNotes] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isOperator = user.role === "WAREHOUSE_OPERATOR";

  useEffect(() => {
    api.recipients().then(setRecipients).catch(() => {});
    api.equipment(id).then(setEquipment).catch(() => {});
    if (id) {
      api.document(id).then((d) => {
        setDoc(d);
        setRecipientId(d.recipient.id);
        setPurpose(d.purpose);
        setIssueDate(d.issue_date);
        setReturnDate(d.expected_return_date);
        setNotes(d.notes);
        setSelected(d.items.map((i) => i.asset_code));
      }).catch(() => {});
    }
  }, [id]);

  const byCode = useMemo(() => Object.fromEntries(equipment.map((e) => [e.asset_code, e])), [equipment]);
  const recipient = recipients.find((r) => r.id === recipientId);
  const manager = users.find((u) => u.role === "HR_MANAGER");
  const operator = isOperator ? user : users.find((u) => u.role === "WAREHOUSE_OPERATOR");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const matches = equipment.filter(
      (e) =>
        !q ||
        e.asset_code.toLowerCase().includes(q) ||
        e.type_name.toLowerCase().includes(q) ||
        e.power.toLowerCase().includes(q),
    );
    // Available items first; issued / reserved ones stay visible but greyed out.
    return [...matches].sort((x, y) => Number(x.availability !== "AVAILABLE") - Number(y.availability !== "AVAILABLE"));
  }, [equipment, search]);

  const toggle = (code: string) =>
    setSelected((s) => (s.includes(code) ? s.filter((c) => c !== code) : [...s, code]));

  async function save(send: boolean) {
    setError(null);
    if (!recipientId) return setError("Select a recipient.");
    if (!purpose.trim()) return setError("Purpose is required.");
    if (selected.length === 0) return setError("Add at least one equipment item.");
    const input: DocumentInput = {
      recipient_user_id: Number(recipientId),
      purpose,
      issue_date: issueDate,
      expected_return_date: returnDate,
      notes,
      equipment_codes: selected,
    };
    setBusy(true);
    let saved: DocumentDetail;
    try {
      saved = id ? await api.update(id, input) : await api.create(input);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Saving failed.");
      setBusy(false);
      return;
    }
    if (send) {
      try {
        const sent = await api.submit(saved.id);
        toast(`${sent.document_number} sent for signatures — waiting for ${sent.actions.next_signer?.full_name}`);
      } catch (e) {
        // The draft exists now; show it rather than risk creating a duplicate.
        toast(`Saved as draft, but not sent: ${e instanceof ApiError ? e.message : "unknown error"}`, "error");
      }
    } else {
      toast(`${saved.document_number} saved as draft`);
    }
    navigate(`/documents/${saved.id}`);
  }

  if (!isOperator) {
    return (
      <div className="page">
        <Notice tone="warn" icon="lock">
          Only the Warehouse Operator can create or edit handover documents. Switch to Rashad Hasanov in the user menu.
        </Notice>
      </div>
    );
  }
  if (id && doc && doc.status !== "DRAFT") {
    return (
      <div className="page">
        <Notice tone="warn" icon="lock">
          {doc.document_number} is locked for signing. Open the document and use “Edit document and invalidate
          signatures” to change it.
        </Notice>
        <button className="btn" onClick={() => navigate(`/documents/${id}`)}>
          Open document
        </button>
      </div>
    );
  }

  return (
    <div className="page">
      <a className="back-link" href={id ? `#/documents/${id}` : "#/"}>
        <Icon name="back" size={14} /> {id ? "Back to document" : "Documents"}
      </a>
      <div className="page-head">
        <div>
          <div className="eyebrow">Warehouse equipment handover</div>
          <h1>
            {id ? (
              <>
                Edit <span className="doc-no doc-no-lg">{doc?.document_number}</span>
              </>
            ) : (
              "New Təhvil-təslim aktı"
            )}
          </h1>
          <p className="page-sub">
            {id
              ? "Draft — changes are allowed until the document is sent for signatures."
              : "A document number is assigned when the draft is saved."}
          </p>
        </div>
        {doc && <StatusChip status={doc.status} />}
      </div>

      {doc && doc.invalidated_signatures.length > 0 && (
        <Notice tone="warn" icon="alert">
          <strong>{doc.invalidated_signatures.length} earlier signature(s) were invalidated</strong> when this document
          was reopened. After saving, send it for signatures again — every signer must sign the new version.
        </Notice>
      )}

      <div className="form-grid">
        <div className="form-col">
          <Panel title="Recipient & handover details">
            <div className="form-fields">
              <label className="form-field">
                <span>Recipient *</span>
                <select value={recipientId} onChange={(e) => setRecipientId(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">Select employee…</option>
                  {recipients.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.full_name} — {r.title}, {r.department_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span>Department</span>
                <input readOnly value={recipient ? `${recipient.department_code} · ${recipient.department_name}` : ""} placeholder="Taken from the recipient" />
              </label>
              <label className="form-field form-field-wide">
                <span>Purpose *</span>
                <input
                  value={purpose}
                  maxLength={500}
                  onChange={(e) => setPurpose(e.target.value)}
                  placeholder="e.g. HR interview recording in studio B"
                />
              </label>
              <label className="form-field">
                <span>Issue date *</span>
                <input type="date" value={issueDate} onChange={(e) => setIssueDate(e.target.value)} />
              </label>
              <label className="form-field">
                <span>Expected return date *</span>
                <input type="date" value={returnDate} min={issueDate} onChange={(e) => setReturnDate(e.target.value)} />
              </label>
              <label className="form-field form-field-wide">
                <span>Notes</span>
                <textarea
                  rows={3}
                  value={notes}
                  maxLength={2000}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Condition, accessories, return instructions…"
                />
              </label>
            </div>
          </Panel>

          <Panel title="Signature chain" aside={<span className="muted">Fixed order · each signer waits for the previous one</span>}>
            <ol className="chain-preview">
              <li>
                <span className="step-no">1</span>
                <span>
                  <strong>Recipient</strong>
                  <small>{recipient?.full_name ?? "Selected employee"}</small>
                </span>
              </li>
              <li>
                <span className="step-no">2</span>
                <span>
                  <strong>HR Manager</strong>
                  <small>{manager?.full_name}</small>
                </span>
              </li>
              <li>
                <span className="step-no">3</span>
                <span>
                  <strong>Warehouse Operator</strong>
                  <small>{operator?.full_name}</small>
                </span>
              </li>
            </ol>
          </Panel>
        </div>

        <div className="form-col">
          <Panel
            title={
              <>
                Equipment <span className="count-badge neutral">{selected.length} selected</span>
              </>
            }
            flush
          >
            <div className="selected-items">
              {selected.length === 0 ? (
                <div className="empty small">No equipment added yet — select items from the register below.</div>
              ) : (
                <table className="table compact">
                  <tbody>
                    {selected.map((code, i) => (
                      <tr key={code}>
                        <td className="col-line">{i + 1}</td>
                        <td>
                          <AssetCode code={code} />
                        </td>
                        <td>{byCode[code]?.description}</td>
                        <td className="muted">{byCode[code] && CATEGORY_LABEL[byCode[code].category]}</td>
                        <td className="col-act">
                          <button className="icon-btn" onClick={() => toggle(code)} aria-label={`Remove ${code}`}>
                            <Icon name="x" size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div className="picker-head">
              <span className="picker-title">Equipment register</span>
              <label className="search">
                <Icon name="search" size={14} />
                <input placeholder="Asset ID or type…" value={search} onChange={(e) => setSearch(e.target.value)} />
              </label>
            </div>
            <div className="picker-list">
              {filtered.map((e) => {
                const isSelected = selected.includes(e.asset_code);
                const unavailable = e.availability !== "AVAILABLE";
                return (
                  <button
                    key={e.asset_code}
                    className={`picker-row${isSelected ? " selected" : ""}`}
                    disabled={unavailable && !isSelected}
                    onClick={() => toggle(e.asset_code)}
                  >
                    <span className={`checkbox${isSelected ? " on" : ""}`}>{isSelected && <Icon name="check" size={12} />}</span>
                    <AssetCode code={e.asset_code} />
                    <span className="picker-desc">
                      {e.type_name}
                      {e.category === "LAMP" ? " lamp" : ""} <span className="muted">· {e.power}</span>
                    </span>
                    <span className="picker-cat">{CATEGORY_LABEL[e.category]}</span>
                    <span className="picker-state">
                      {e.availability === "AVAILABLE" && <span className="muted">{e.location}</span>}
                      {e.availability === "ISSUED" && (
                        <span className="text-red">Issued · {e.holder_name}</span>
                      )}
                      {e.availability === "RESERVED" && (
                        <span className="text-amber">On {e.reserved_document_number}</span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          </Panel>
        </div>
      </div>

      <div className="form-footer">
        {error && (
          <div className="form-error">
            <Icon name="alert" size={15} /> {error}
          </div>
        )}
        <span className="muted footer-hint">
          Sending locks the content and calculates its SHA-256 fingerprint. Signers sign that exact fingerprint.
        </span>
        <button className="btn" disabled={busy} onClick={() => navigate(id ? `/documents/${id}` : "/")}>
          Cancel
        </button>
        <button className="btn" disabled={busy} onClick={() => save(false)}>
          Save draft
        </button>
        <button className="btn btn-primary" disabled={busy} onClick={() => save(true)}>
          <Icon name="send" /> Save & send for signatures
        </button>
      </div>
    </div>
  );
}
