// The last screen of the guided set-up: everything the root admin chose, as saved on the server, one block per step with an
// Edit button that opens that step again. Nothing here changes data.
import { Building2, CalendarDays, Hospital, Pencil, PlugZap, Users } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { DateText } from "@/components/DateText";
import type { AccountRow, SetupResponse } from "@/lib/types";
import { formFrom, PLACEHOLDER_DOMAIN, WEEKDAYS } from "@/features/admin/state";

const LEVEL: Record<string, string> = { essential: "Essential", optimal: "Optimal", optional: "Optional" };
const ROLE: Record<string, string> = { member: "Doctor", head: "Head", resident: "Resident" };

function Block({ icon: Icon, title, onEdit, children }: { icon: typeof Hospital; title: string; onEdit: () => void; children: ReactNode }) {
  return (
    <section className="surface-inner p-4" aria-label={title}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm"><Icon className="size-4 text-brand" aria-hidden /> {title}</h3>
        <Button type="button" variant="ghost" size="sm" onClick={onEdit}><Pencil className="size-3.5" aria-hidden /> Edit</Button>
      </div>
      <div className="text-sm text-body">{children}</div>
    </section>
  );
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="grid grid-cols-[160px_1fr] gap-2 py-0.5">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="min-w-0 break-words text-foreground">{v}</dd>
    </div>
  );
}

export function SetupReview({ setup, accounts, onEdit }: { setup: SetupResponse; accounts: AccountRow[]; onEdit: (step: number) => void }) {
  const f = formFrom(setup);
  const deptName = (id: string) => setup.departments.find((d) => d.id === id)?.name || id;
  const enabled = setup.departments.filter((d) => d.enabled);
  const treating = enabled.filter((d) => d.group === "treating").length;
  const supporting = enabled.filter((d) => d.group === "supporting").length;
  const contacts = enabled.filter((d) => (d.email && !d.email.endsWith(`@${PLACEHOLDER_DOMAIN}`)) || d.phone);
  const people = accounts.filter((a) => a.account !== false);
  const coordinators = f.board.coordinators.map((u) => accounts.find((a) => a.username === u)?.display_name || u);
  const his = setup.his;
  return (
    <div className="grid w-full gap-3 text-left">
      <Block icon={Hospital} title="Hospital" onEdit={() => onEdit(1)}>
        <dl>
          <Row k="Name" v={f.hospital.name || "not given"} />
          <Row k="NCG level" v={LEVEL[f.hospital.level] || f.hospital.level} />
          {f.hospital.type ? <Row k="Type" v={f.hospital.type} /> : null}
          <Row k="PM-JAY" v={f.hospital.pmjay ? "Empanelled" : "Not empanelled"} />
          <Row k="Records fetched" v={`${f.hospital.fetchWindow} months for a new Case File`} />
        </dl>
      </Block>
      <Block icon={Building2} title="Departments" onEdit={() => onEdit(2)}>
        <p>{treating} treating and {supporting} supporting departments.</p>
        {contacts.length ? (
          <ul className="mt-2 grid gap-1">
            {contacts.map((d) => (
              <li key={d.id}><span className="text-foreground">{d.name}</span>: {[d.email && !d.email.endsWith(`@${PLACEHOLDER_DOMAIN}`) ? d.email : "", d.phone].filter(Boolean).join(", ")}</li>
            ))}
          </ul>
        ) : <p className="mt-1 text-muted-foreground">No desk contacts given yet.</p>}
      </Block>
      <Block icon={Users} title={`People and roles (${people.length})`} onEdit={() => onEdit(3)}>
        {people.length ? (
          <ul className="grid gap-1">
            {people.map((a) => {
              const roles = [
                ...Object.entries(a.departments ?? {}).map(([d, r]) => `${ROLE[r] || r}, ${deptName(d)}`),
                ...(a.admin_of ?? []).map((d) => `Department admin, ${deptName(d)}`),
                a.coordinator ? "MDT Coordinator" : "",
                a.root_admin ? "Root admin" : "",
                a.auditor ? "Auditor" : "",
              ].filter(Boolean);
              return (
                <li key={a.username} className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-foreground">{a.display_name || a.username}</span>
                  <span className="mono text-xs text-muted-foreground">{a.username}</span>
                  <span className="text-muted-foreground">{roles.join("; ") || "no role yet"}</span>
                  {a.end_date ? <span className="text-muted-foreground">until <DateText value={a.end_date} /></span> : null}
                  {a.must_change_password ? <span className="text-xs text-warn">has not signed in yet</span> : null}
                </li>
              );
            })}
          </ul>
        ) : <p className="text-muted-foreground">Nobody yet.</p>}
      </Block>
      <Block icon={PlugZap} title="Hospital system" onEdit={() => onEdit(4)}>
        <dl>
          <Row k="Address" v={<span className="mono">{his?.url || "not set"}</span>} />
          <Row k="Last test" v={his?.ok ? <span className="text-ok">answered{his.tested_at ? <> on <DateText value={his.tested_at} /></> : null}</span> : <span className="text-bad">not passed yet</span>} />
        </dl>
      </Block>
      <Block icon={CalendarDays} title="Board" onEdit={() => onEdit(5)}>
        <dl>
          <Row k="MDT Coordinators" v={coordinators.join(", ") || "none yet"} />
          <Row k="Heads at every board" v={f.board.heads.map(deptName).join(", ")} />
          <Row k="Meetings" v={[f.board.weekday && WEEKDAYS.includes(f.board.weekday) ? `${f.board.weekday}s` : "No fixed day", f.board.time, f.board.room].filter(Boolean).join(", ")} />
          <Row k="Minutes per case" v={String(f.board.minutes)} />
        </dl>
      </Block>
    </div>
  );
}
