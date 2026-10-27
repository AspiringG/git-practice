import { useEffect, useRef, useState } from "react";
import { DEMO_PINS, useApp } from "../context";
import { navigate } from "../router";
import { Icon } from "./Icon";
import { Avatar } from "./ui";

export function Header({ section }: { section: "documents" | "equipment" }) {
  const { user, users, switchUser, resetDemo } = useApp();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <a className="brand" href="#/">
          <span className="brand-mark">X</span>
          <span className="brand-name">
            XEZER <span>ERP</span>
          </span>
        </a>
        <span className="topbar-sep" />
        <span className="module-name">Anbar · e-İmza</span>
        <span className="proto-tag" title="Prototype — internal electronic signature concept. Not a qualified electronic signature.">
          Prototype
        </span>

        <nav className="topnav">
          <a className={section === "documents" ? "active" : ""} href="#/">
            <Icon name="doc" size={15} /> Sənədlər
          </a>
          <a className={section === "equipment" ? "active" : ""} href="#/equipment">
            <Icon name="box" size={15} /> Avadanlıq
          </a>
        </nav>

        <div className="user-menu" ref={menuRef}>
          <button className="user-btn" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
            <Avatar name={user.full_name} />
            <span className="user-btn-text">
              <strong>{user.full_name}</strong>
              <small>{user.title}</small>
            </span>
            <Icon name="chevron" size={14} />
          </button>
          {open && (
            <div className="user-dropdown" role="menu">
              <div className="dropdown-label">Switch demo user</div>
              {users.map((u) => (
                <button
                  key={u.id}
                  role="menuitem"
                  className={`dropdown-user${u.id === user.id ? " current" : ""}`}
                  onClick={async () => {
                    setOpen(false);
                    if (u.id !== user.id) await switchUser(u.id);
                  }}
                >
                  <Avatar name={u.full_name} small />
                  <span>
                    <strong>{u.full_name}</strong>
                    <small>{u.title}</small>
                  </span>
                  <span className="demo-pin">PIN {DEMO_PINS[u.id] ?? "—"}</span>
                  {u.id === user.id && <Icon name="check" size={14} className="dropdown-check" />}
                </button>
              ))}
              <div className="dropdown-sep" />
              <button
                className="dropdown-action"
                onClick={async () => {
                  setOpen(false);
                  if (window.confirm("Reset all demo data to the initial seeded state?")) {
                    await resetDemo();
                    navigate("/");
                  }
                }}
              >
                <Icon name="refresh" size={14} /> Reset demo data
              </button>
              <div className="dropdown-foot">Demo users only · PINs are demo credentials</div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
