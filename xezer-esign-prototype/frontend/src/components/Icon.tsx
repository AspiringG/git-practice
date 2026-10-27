const PATHS: Record<string, string> = {
  check: "M4 10.5l3.5 3.5L16 6",
  plus: "M10 4v12M4 10h12",
  back: "M12 4l-6 6 6 6",
  lock: "M6 9V7a4 4 0 118 0v2M5 9h10v8H5z",
  print: "M6 8V3h8v5M6 14H4V8h12v6h-2M6 12h8v5H6z",
  edit: "M4 16h3l8-8-3-3-8 8v3zM11 6l3 3",
  pen: "M3 17l1-4 9-9 3 3-9 9-4 1zM12 5l3 3",
  shield: "M10 2l6 2.5v5c0 4-2.6 6.8-6 8.5-3.4-1.7-6-4.5-6-8.5v-5L10 2zM7 10l2 2 4-4",
  alert: "M10 3l8 14H2L10 3zM10 8v4M10 14.5v.5",
  x: "M5 5l10 10M15 5L5 15",
  search: "M9 15a6 6 0 100-12 6 6 0 000 12zM13.5 13.5L17 17",
  box: "M3 6l7-3 7 3v8l-7 3-7-3V6zM3 6l7 3 7-3M10 9v8",
  send: "M3 10l14-6-5 14-3-6-6-2zM9 12l3-3",
  user: "M10 10a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM3.5 17c.8-3 3.3-4.5 6.5-4.5s5.7 1.5 6.5 4.5",
  swap: "M5 7h11l-3-3M15 13H4l3 3",
  chevron: "M6 8l4 4 4-4",
  refresh: "M16 10a6 6 0 11-1.8-4.3M16 3v4h-4",
  doc: "M5 2h7l4 4v12H5V2zM12 2v4h4M8 10h6M8 13h6",
  release: "M3 10h10M9 5l5 5-5 5M16 4v12",
  ban: "M10 17a7 7 0 100-14 7 7 0 000 14zM5 5l10 10",
  fingerprint: "M6 16c1-2 1.5-4 1.5-6.5a2.5 2.5 0 015 0c0 3-.5 5.5-1.5 7.5M10 9.5c0 3-.6 5.3-2 7.5M4 13c.4-1.2.5-2.3.5-3.5a5.5 5.5 0 0111 0c0 1.5-.1 2.8-.4 4",
};

export function Icon({ name, size = 16, className }: { name: keyof typeof PATHS | string; size?: number; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
