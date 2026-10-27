import type { Status } from "./types";

// Demo times are shown in Baku time regardless of the presenting laptop's settings.
const TZ = "Asia/Baku";

const dtf = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function parts(iso: string) {
  const p = Object.fromEntries(dtf.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return { day: `${p.day}.${p.month}.${p.year}`, time: `${p.hour}:${p.minute}` };
}

export const fmtDateTime = (iso: string | null) => (iso ? `${parts(iso).day} ${parts(iso).time}` : "—");
export const fmtTime = (iso: string) => parts(iso).time;
export const fmtDay = (iso: string) => parts(iso).day;

/** Calendar dates (YYYY-MM-DD) are not instants — format without time-zone shifts. */
export function fmtDate(isoDate: string | null) {
  if (!isoDate) return "—";
  const [y, m, d] = isoDate.split("-");
  return `${d}.${m}.${y}`;
}

export function todayIso() {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "2-digit", month: "2-digit", year: "numeric" })
      .formatToParts(new Date())
      .map((x) => [x.type, x.value]),
  );
  return `${p.year}-${p.month}-${p.day}`;
}

export function addDays(isoDate: string, days: number) {
  const d = new Date(`${isoDate}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export const shortHash = (h: string | null) => (h ? `${h.slice(0, 4)}…${h.slice(-4)}`.toUpperCase() : "—");
export const groupedHash = (h: string) => h.toUpperCase().match(/.{1,4}/g)!.join(" ");

export const initials = (name: string) =>
  name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

export const STATUS_META: Record<Status, { label: string; az: string; tone: string }> = {
  DRAFT: { label: "Draft", az: "Qaralama", tone: "gray" },
  WAITING_FOR_SIGNATURES: { label: "Waiting for signatures", az: "İmza gözləyir", tone: "amber" },
  SIGNED: { label: "Fully signed", az: "İmzalanıb", tone: "blue" },
  RELEASED: { label: "Released", az: "Təhvil verilib", tone: "green" },
  CANCELLED: { label: "Cancelled", az: "Ləğv edilib", tone: "red" },
};

export const STATUS_ORDER: Status[] = ["DRAFT", "WAITING_FOR_SIGNATURES", "SIGNED", "RELEASED", "CANCELLED"];

export const CATEGORY_LABEL = { PRIBOR: "Pribor", LAMP: "Lamp" } as const;
