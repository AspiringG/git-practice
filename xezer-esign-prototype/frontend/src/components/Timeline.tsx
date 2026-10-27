import { fmtDay, fmtTime } from "../format";
import type { AuditEvent } from "../types";

const TONE: Record<string, string> = {
  CREATED: "gray",
  UPDATED: "gray",
  SUBMITTED: "blue",
  SIGNED: "green",
  FULLY_SIGNED: "blue",
  RELEASED: "green",
  SIGNATURES_INVALIDATED: "amber",
  REOPENED: "amber",
  CANCELLED: "red",
};

export function Timeline({ events }: { events: AuditEvent[] }) {
  const days: { day: string; events: AuditEvent[] }[] = [];
  for (const e of events) {
    const day = fmtDay(e.occurred_at);
    if (days.length === 0 || days[days.length - 1].day !== day) days.push({ day, events: [] });
    days[days.length - 1].events.push(e);
  }
  return (
    <div className="timeline">
      {days.map((d) => (
        <div key={d.day} className="tl-day">
          <div className="tl-date">{d.day}</div>
          <ol>
            {d.events.map((e) => (
              <li key={e.id} className={`tl-item tone-${TONE[e.event_type] ?? "gray"}`}>
                <span className="tl-time">{fmtTime(e.occurred_at)}</span>
                <span className="tl-dot" />
                <div className="tl-body">
                  <div className="tl-title">{e.description}</div>
                  {e.actor_name && (
                    <div className="tl-actor">
                      {e.actor_name}
                      {e.actor_title && <span> · {e.actor_title}</span>}
                    </div>
                  )}
                  {e.detail && <div className="tl-detail">{e.detail}</div>}
                </div>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}
