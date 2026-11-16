// /platform (Overview): tiles, one row per hospital, and "Needs attention" (GET /platform/overview). Counts only, no patient data.
import { Link } from "react-router-dom";
import { AlertTriangle, Building2, CalendarDays, CheckCircle2, ChevronRight, FolderOpen, KeyRound, PauseCircle, PlugZap, ShieldCheck, UserRoundX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { DateText } from "@/components/DateText";
import { usePlatformOverview } from "@/hooks/useQueries";
import type { HospitalRow, PlatformAttention } from "@/lib/types";
import { Card, CardSkeleton, HisPill, HospitalStatusPill, SetupProgress, StatTile, TileGrid } from "@/features/consoles/shared";
import { usePlatformContext } from "@/features/consoles/platform/PlatformConsole";

const ATTENTION_ICON = { no_admin: UserRoundX, setup_unfinished: AlertTriangle, his_failing: PlugZap, admin_never_signed_in: KeyRound } as const;

export function HospitalsTable({ rows }: { rows: HospitalRow[] }) {
  return (
    <>
      {/* Laptop: a table. */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm" aria-label="Hospitals">
          <thead>
            <tr className="border-b border-border text-left text-xs font-medium text-muted-foreground">
              <th scope="col" className="py-2 pr-3 font-medium">Hospital</th>
              <th scope="col" className="px-3 py-2 font-medium">Status</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Admins</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">People</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Case Files</th>
              <th scope="col" className="px-3 py-2 font-medium">Set-up</th>
              <th scope="col" className="px-3 py-2 font-medium">Hospital system</th>
              <th scope="col" className="py-2 pl-3 font-medium">Last activity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h) => (
              <tr key={h.id} className="group border-b border-border last:border-0 hover:bg-accent/50">
                <td className="py-2.5 pr-3">
                  <Link to={`/platform/hospitals/${encodeURIComponent(h.id)}`} className="font-medium text-foreground outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring">{h.name}</Link>
                  <span className="block text-xs text-muted-foreground">{[h.city, h.state].filter(Boolean).join(", ") || "Place not given"}</span>
                </td>
                <td className="px-3 py-2.5"><HospitalStatusPill status={h.status} /></td>
                <td className={h.admins ? "px-3 py-2.5 text-right tabular-nums" : "px-3 py-2.5 text-right tabular-nums font-medium text-bad"}>{h.admins}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{h.people}</td>
                <td className="px-3 py-2.5 text-right tabular-nums" title={`${h.case_files.open} open, ${h.case_files.decided} decided`}>{h.case_files.open} <span className="text-muted-foreground">/ {h.case_files.decided}</span></td>
                <td className="px-3 py-2.5"><SetupProgress done={h.setup.done} total={h.setup.total} /></td>
                <td className="px-3 py-2.5"><HisPill his={h.his} /></td>
                <td className="py-2.5 pl-3 text-xs text-muted-foreground">{h.last_activity ? <DateText value={h.last_activity} mode="ago" /> : "None yet"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-muted-foreground">Case Files: open / decided.</p>
      </div>
      {/* Phone: one card per hospital. */}
      <ul className="grid grid-cols-1 gap-2 md:hidden" aria-label="Hospitals">
        {rows.map((h) => (
          <li key={h.id}>
            <Link to={`/platform/hospitals/${encodeURIComponent(h.id)}`} className="surface-inner row-lift flex flex-col gap-2 p-3 outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <span className="flex items-start justify-between gap-2">
                <span className="min-w-0">
                  <span className="block font-medium text-foreground">{h.name}</span>
                  <span className="block text-xs text-muted-foreground">{[h.city, h.state].filter(Boolean).join(", ") || "Place not given"}</span>
                </span>
                <HospitalStatusPill status={h.status} />
              </span>
              <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span><span className="font-medium tabular-nums text-foreground">{h.admins}</span> {h.admins === 1 ? "admin" : "admins"}</span>
                <span><span className="font-medium tabular-nums text-foreground">{h.people}</span> people</span>
                <span><span className="font-medium tabular-nums text-foreground">{h.case_files.open}</span> open Case Files</span>
              </span>
              <span className="flex flex-wrap items-center gap-2"><SetupProgress done={h.setup.done} total={h.setup.total} /><HisPill his={h.his} /></span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

export function AttentionList({ items, empty, columns }: { items: Array<PlatformAttention & { link?: string }>; empty: string; columns?: boolean }) {
  if (!items.length) return <p className="flex items-center gap-2 text-sm text-muted-foreground"><CheckCircle2 className="size-4 text-ok" aria-hidden /> {empty}</p>;
  return (
    <ul className={columns ? "grid grid-cols-1 gap-1.5 md:grid-cols-2" : "grid grid-cols-1 gap-1.5"}>
      {items.map((a, i) => {
        const Icon = ATTENTION_ICON[a.kind as keyof typeof ATTENTION_ICON] ?? AlertTriangle;
        const to = a.link || (a.hospital ? `/platform/hospitals/${encodeURIComponent(a.hospital)}` : undefined);
        const inner = (
          <>
            <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md status-warn"><Icon className="size-4" aria-hidden /></span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm text-foreground">{a.text}</span>
              {a.hospital_name ? <span className="block text-xs text-muted-foreground">{a.hospital_name}</span> : null}
            </span>
            {to ? <ChevronRight className="mt-1 size-4 shrink-0 text-muted-foreground" aria-hidden /> : null}
          </>
        );
        return (
          <li key={`${a.kind}-${a.hospital}-${i}`}>
            {to ? <Link to={to} className="flex items-start gap-3 rounded-md p-2 outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring">{inner}</Link> : <div className="flex items-start gap-3 p-2">{inner}</div>}
          </li>
        );
      })}
    </ul>
  );
}

export default function PlatformOverview() {
  const q = usePlatformOverview();
  const { openAddHospital } = usePlatformContext();
  const t = q.data?.tiles ?? {};
  const loading = q.isLoading;
  if (q.error && !q.data) return <div className="surface"><ErrorState error={q.error} what="the Vaidyx console" onRetry={() => void q.refetch()} retrying={q.isFetching} /></div>;
  const hospitals = q.data?.hospitals ?? [];
  const total = (t.hospitals_active ?? 0) + (t.hospitals_suspended ?? 0) || hospitals.length;
  return (
    <div className="grid grid-cols-1 gap-5">
      <TileGrid>
        <StatTile loading={loading} value={t.hospitals_active} label="Hospitals active" icon={Building2} to="/platform/hospitals" />
        <StatTile loading={loading} value={t.logins} label="Logins" icon={KeyRound} to="/platform/logins" />
        <StatTile loading={loading} value={t.case_files} label="Case Files, all hospitals" icon={FolderOpen} />
        <StatTile loading={loading} value={t.meetings_next_7_days} label="Meetings in the next 7 days" icon={CalendarDays} />
        <StatTile loading={loading} value={`${t.setup_complete ?? 0} of ${total}`} label="Set-up complete" icon={ShieldCheck} tone={total && (t.setup_complete ?? 0) >= total ? "ok" : "neutral"} />
        <StatTile loading={loading} value={`${t.his_connected ?? 0} of ${total}`} label="Hospital systems connected" icon={PlugZap} tone={total && (t.his_connected ?? 0) >= total ? "ok" : "neutral"} />
        <StatTile loading={loading} value={t.hospital_admins} label="Hospital admins" icon={ShieldCheck} />
        <StatTile loading={loading} value={t.hospitals_suspended} label="Suspended" icon={PauseCircle} tone={t.hospitals_suspended ? "warn" : "neutral"} />
      </TileGrid>
      <Card title="Needs attention" icon={AlertTriangle} id="ov-attention">
        {loading ? <CardSkeleton lines={3} /> : <AttentionList items={q.data?.attention ?? []} empty="Nothing needs you now." columns />}
      </Card>
      <Card title="Hospitals" icon={Building2} id="ov-hospitals" action={<Button type="button" variant="ghost" size="sm" asChild><Link to="/platform/hospitals">All hospitals <ChevronRight className="size-4" aria-hidden /></Link></Button>} className="min-w-0">
        {loading ? <CardSkeleton lines={4} /> : hospitals.length ? <HospitalsTable rows={hospitals} /> : (
          <EmptyState compact kind="empty" title="No hospital yet" text="Add the first hospital and its admin." action={<Button type="button" onClick={openAddHospital}>Add a hospital</Button>} />
        )}
      </Card>
    </div>
  );
}
