import { createContext, useContext } from "react";
import type { User } from "./types";

export type ToastTone = "ok" | "error" | "info";

export interface AppContextValue {
  user: User;
  users: User[];
  switchUser: (id: number) => Promise<void>;
  toast: (message: string, tone?: ToastTone) => void;
  resetDemo: () => Promise<void>;
  /** Bumped after user switch / reset so pages refetch. */
  version: number;
}

export const AppContext = createContext<AppContextValue | null>(null);

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside provider");
  return ctx;
}

export const DEMO_PINS: Record<number, string> = { 1: "1111", 2: "2222", 3: "3333" };
