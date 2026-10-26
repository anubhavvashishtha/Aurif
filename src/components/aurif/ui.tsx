import { Link, useNavigate } from "@tanstack/react-router";
import { Activity, ExternalLink, KeyRound, LayoutGrid, LogOut, SlidersHorizontal, Terminal } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { isBlockedKind, logout, setActiveSite, useAurif, type EventKind } from "@/lib/aurif-store";

export const CUSTOMER_SITE_URL = "https://fieldhouse.shop";

export function Brand({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-serif text-xl font-semibold tracking-tight text-ink", className)}>
      <span className="grid h-7 w-7 place-items-center rounded-md bg-ink font-serif text-sm text-ink-foreground">A</span>
      Aurif
    </span>
  );
}

export function Topbar({ label = "Dashboard" }: { label?: string }) {
  const email = useAurif((s) => s.user?.email);
  const navigate = useNavigate();
  return (
    <header className="sticky top-0 z-20 border-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 md:px-6">
        <Link to="/dashboard"><Brand /></Link>
        <span className="hidden text-sm text-muted-foreground sm:inline">/ {label}</span>
        <div className="ml-auto flex items-center gap-1 sm:gap-2">
          <Button variant="ghost" size="sm" asChild>
            <a href={CUSTOMER_SITE_URL} target="_blank" rel="noreferrer">
              <span className="hidden sm:inline">Customer site</span><ExternalLink />
            </a>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to="/console"><Terminal /> <span className="hidden sm:inline">Agent console</span></Link>
          </Button>
          {email && (
            <>
              <span className="hidden font-mono text-xs text-muted-foreground lg:inline">{email}</span>
              <Button variant="ghost" size="sm" onClick={() => { logout(); navigate({ to: "/", replace: true }); }}>
                <LogOut /> <span className="hidden sm:inline">Log out</span>
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

const NAV = [
  { to: "/dashboard", label: "Overview", icon: LayoutGrid },
  { to: "/dashboard/activity", label: "Agent activity", icon: Activity },
  { to: "/dashboard/endpoints", label: "Endpoint control", icon: SlidersHorizontal },
  { to: "/dashboard/credentials", label: "Site credentials", icon: KeyRound },
] as const;

export function SiteSwitcher() {
  const sites = useAurif((s) => s.sites);
  const active = useAurif((s) => s.activeSiteId);
  return (
    <Select value={active} onValueChange={setActiveSite}>
      <SelectTrigger className="w-full bg-card"><SelectValue /></SelectTrigger>
      <SelectContent>
        {sites.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

export function SideNav() {
  return (
    <aside className="md:w-56 md:shrink-0">
      <div className="space-y-4 md:sticky md:top-20">
        <div>
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">Site</p>
          <SiteSwitcher />
        </div>
        <nav className="flex gap-1 overflow-x-auto md:flex-col">
          {NAV.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              activeOptions={{ exact: true }}
              className="flex items-center gap-2.5 whitespace-nowrap rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground data-[status=active]:bg-accent data-[status=active]:font-medium data-[status=active]:text-accent-foreground"
            >
              <Icon className="h-4 w-4" /> {label}
            </Link>
          ))}
        </nav>
      </div>
    </aside>
  );
}

export function PageHeader({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-3xl font-medium text-ink">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("rounded-xl border bg-card shadow-soft", className)}>{children}</div>;
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: "danger" }) {
  return (
    <div className="px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("mt-2 font-serif text-3xl text-ink", tone === "danger" && "text-destructive")}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "ok" | "danger" | "muted" }) {
  const tones = {
    neutral: "bg-secondary text-secondary-foreground",
    ok: "bg-accent text-accent-foreground",
    danger: "bg-danger-soft text-destructive",
    muted: "bg-muted text-muted-foreground",
  };
  return <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 font-mono text-[11px]", tones[tone])}>{children}</span>;
}

export function EventBadge({ kind }: { kind: EventKind }) {
  return <Badge tone={isBlockedKind(kind) ? "danger" : kind === "handshake" ? "neutral" : "ok"}>{kind}</Badge>;
}

export function DataTable<T>({ columns, rows, rowKey, rowClass, empty }: {
  columns: { header: string; cell: (r: T) => ReactNode; className?: string }[];
  rows: T[];
  rowKey: (r: T) => string;
  rowClass?: (r: T) => string;
  empty?: ReactNode;
}) {
  if (!rows.length) return <div className="px-6 py-16 text-center text-sm text-muted-foreground">{empty}</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
            {columns.map((c) => <th key={c.header} className={cn("px-5 py-3 font-medium", c.className)}>{c.header}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)} className={cn("border-b last:border-0 transition-colors hover:bg-muted/50", rowClass?.(r))}>
              {columns.map((c) => <td key={c.header} className={cn("px-5 py-3", c.className)}>{c.cell(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ToggleRow({ label, kind, refId, checked, onChange }: {
  label: string; kind: "page" | "action"; refId: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-4 px-5 py-3.5">
      <div className="min-w-0 flex-1">
        <p className="font-medium text-foreground">{label}</p>
        <p className="truncate font-mono text-xs text-muted-foreground">{refId}</p>
      </div>
      <Badge tone="muted">{kind}</Badge>
      <span className={cn("hidden w-8 text-right font-mono text-xs sm:inline", checked ? "text-primary" : "text-muted-foreground")}>
        {checked ? "ON" : "OFF"}
      </span>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={`Agent access for ${label}`} />
    </div>
  );
}

export function AuthCard({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="grid min-h-screen bg-background bg-wash lg:grid-cols-2">
      <div className="hidden flex-col justify-between p-12 lg:flex">
        <Brand className="text-2xl" />
        <div className="animate-rise max-w-md">
          <h2 className="font-serif text-5xl leading-[1.05] text-ink">Decide what AI agents can see on your site.</h2>
          <p className="mt-5 text-muted-foreground">
            Aurif is a permission layer for AI traffic. Share pages and actions with agents the way you share a document — and see every read.
          </p>
        </div>
        <p className="font-mono text-xs text-muted-foreground">agent → handshake → scoped access → audit</p>
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="animate-rise w-full max-w-sm">
          <Brand className="mb-8 text-2xl lg:hidden" />
          <h1 className="text-3xl text-ink">{title}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">{subtitle}</p>
          <div className="mt-8">{children}</div>
          <div className="mt-6 text-sm text-muted-foreground">{footer}</div>
        </div>
      </div>
    </div>
  );
}

export const shortKey = (k: string) => `${k.slice(0, 12)}…${k.slice(-4)}`;
