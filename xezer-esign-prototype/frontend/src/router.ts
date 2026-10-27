import { useEffect, useState } from "react";

/** Minimal hash router: "#/documents/12" → ["documents", "12"]. */
export function useRoute(): string[] {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash.replace(/^#\/?/, "").split("/").filter(Boolean);
}

export function navigate(path: string) {
  window.location.hash = path;
  window.scrollTo(0, 0);
}
