import { useEffect, useState } from "react";
import { api } from "../api";
import { AssetCode, Panel } from "../components/ui";
import { CATEGORY_LABEL } from "../format";
import type { Equipment } from "../types";

export function EquipmentPage() {
  const [items, setItems] = useState<Equipment[] | null>(null);
  useEffect(() => {
    api.equipment().then(setItems).catch(() => setItems([]));
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="eyebrow">Anbar</div>
          <h1>Avadanlıq reyestri</h1>
          <p className="page-sub">Equipment register — permanent asset IDs and current availability</p>
        </div>
      </div>
      <Panel title={<>Equipment <span className="count-badge neutral">{items?.length ?? "–"}</span></>} flush>
        <table className="table">
          <thead>
            <tr>
              <th>Asset ID</th>
              <th>Type</th>
              <th>Category</th>
              <th>Power</th>
              <th>Location</th>
              <th>Availability</th>
            </tr>
          </thead>
          <tbody>
            {items?.map((e) => (
              <tr key={e.asset_code}>
                <td>
                  <AssetCode code={e.asset_code} large />
                </td>
                <td>{e.category === "LAMP" ? `${e.type_name} lamp` : e.type_name}</td>
                <td className="muted">{CATEGORY_LABEL[e.category]}</td>
                <td>{e.power}</td>
                <td className="muted">{e.location}</td>
                <td>
                  {e.availability === "AVAILABLE" && <span className="chip chip-green"><span className="chip-dot" />In stock</span>}
                  {e.availability === "RESERVED" && (
                    <span className="chip chip-amber"><span className="chip-dot" />On {e.reserved_document_number}</span>
                  )}
                  {e.availability === "ISSUED" && (
                    <span className="chip chip-blue">
                      <span className="chip-dot" />Issued to {e.holder_name} · {e.issued_document_number}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
