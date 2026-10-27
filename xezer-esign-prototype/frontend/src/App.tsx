import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Header } from "./components/Header";
import { AppContext, type AppContextValue, type ToastTone } from "./context";
import { Dashboard } from "./pages/Dashboard";
import { DocumentDetailPage } from "./pages/DocumentDetail";
import { DocumentForm } from "./pages/DocumentForm";
import { EquipmentPage } from "./pages/EquipmentPage";
import { PrintView } from "./pages/PrintView";
import { useRoute } from "./router";
import type { User } from "./types";

const DEFAULT_USER_ID = 3; // Rashad Hasanov — Warehouse Operator starts the demo

interface Toast {
  id: number;
  message: string;
  tone: ToastTone;
}

export function App() {
  const route = useRoute();
  const [user, setUser] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [version, setVersion] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setUsers(await api.users());
        let me: User | null = null;
        if (api.hasToken()) me = await api.me().catch(() => null);
        setUser(me ?? (await api.login(DEFAULT_USER_ID)));
      } catch {
        setBootError("Cannot reach the prototype backend. Start it with: uvicorn app.main:app --reload");
      }
    })();
  }, []);

  useEffect(() => {
    if (!user) return;
    const onExpired = async () => {
      setUser(await api.login(user.id).catch(() => api.login(DEFAULT_USER_ID)));
      setVersion((v) => v + 1);
    };
    window.addEventListener("esign-session-expired", onExpired);
    return () => window.removeEventListener("esign-session-expired", onExpired);
  }, [user]);

  const toast = useCallback((message: string, tone: ToastTone = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-2), { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  const switchUser = useCallback(
    async (id: number) => {
      const u = await api.login(id);
      setUser(u);
      setVersion((v) => v + 1);
      toast(`Now working as ${u.full_name} · ${u.title}`, "info");
    },
    [toast],
  );

  const resetDemo = useCallback(async () => {
    await api.resetDemo();
    const u = await api.login(user?.id ?? DEFAULT_USER_ID);
    setUser(u);
    setVersion((v) => v + 1);
    toast("Demo data reset to the initial state", "info");
  }, [toast, user]);

  const ctx = useMemo<AppContextValue | null>(
    () => (user ? { user, users, switchUser, toast, resetDemo, version } : null),
    [user, users, switchUser, toast, resetDemo, version],
  );

  if (bootError) return <div className="boot-message error">{bootError}</div>;
  if (!ctx) return <div className="boot-message">Loading…</div>;

  const [a, b, c] = route;
  const docId = a === "documents" && b && b !== "new" ? Number(b) : null;

  if (docId && c === "print") {
    return (
      <AppContext.Provider value={ctx}>
        <PrintView key={`${docId}-${version}`} id={docId} />
      </AppContext.Provider>
    );
  }

  let page;
  if (a === "equipment") page = <EquipmentPage key={version} />;
  else if (a === "documents" && b === "new") page = <DocumentForm key={`new-${version}`} />;
  else if (docId && c === "edit") page = <DocumentForm key={`${docId}-${version}`} id={docId} />;
  else if (docId) page = <DocumentDetailPage key={`${docId}-${version}`} id={docId} />;
  else page = <Dashboard key={version} />;

  return (
    <AppContext.Provider value={ctx}>
      <div className="app">
        <Header section={a === "equipment" ? "equipment" : "documents"} />
        <main className="workspace">{page}</main>
        <footer className="disclaimer">
          Prototype — internal electronic signature concept · Not a qualified electronic signature
        </footer>
      </div>
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            {t.message}
          </div>
        ))}
      </div>
    </AppContext.Provider>
  );
}
