import { Link, useNavigate } from "@tanstack/react-router";
import { Activity, Bot, ExternalLink, KeyRound, LayoutGrid, LogOut, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { isBlockedKind, logout, setActiveSite, useAurif, type EventKind } from "@/lib/aurif-store";

export const CUSTOMER_SITE_URL = import.meta.env.VITE_CUSTOMER_SITE_URL ?? "http://127.0.0.1:5173";

export function Brand({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-mono text-sm font-medium uppercase tracking-[0.18em] text-ink", className)}>
      <span className="grid h-7 w-7 place-items-center border border-ink bg-ink font-mono text-[11px] text-ink-foreground">A</span>
      Aurif
    </span>
  );
}

export function Topbar({ label = "Dashboard" }: { label?: string }) {
  const email = useAurif((s) => s.user?.email);
  const navigate = useNavigate();
  return (
    <header className="sticky top-0 z-20 border-b border-ink/80 bg-frost">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 md:px-6">
        <Link to="/dashboard"><Brand /></Link>
        <span className="hidden font-mono text-[11px] uppercase tracking-widest text-muted-foreground sm:inline">// {label}</span>
        <div className="ml-auto flex items-center gap-1 sm:gap-2">
          <Button variant="ghost" size="sm" asChild>
            <a href={CUSTOMER_SITE_URL} target="_blank" rel="noreferrer">
              <span className="hidden sm:inline">Customer site</span><ExternalLink />
            </a>
          </Button>
          {email && (
            <>
              <span className="hidden font-mono text-xs text-muted-foreground lg:inline">{email}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  await logout();
                  navigate({ to: "/", replace: true });
                }}
              >
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
  { to: "/dashboard/agent", label: "Agent dashboard", icon: Bot },
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
      <div className="space-y-4 rounded-sm border border-ink/15 bg-frost p-3 md:sticky md:top-20">
        <div>
          <p className="mb-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">Active site</p>
          <SiteSwitcher />
        </div>
        <nav className="flex gap-1 overflow-x-auto md:flex-col">
          {NAV.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              activeOptions={{ exact: true }}
              className="flex items-center gap-2.5 whitespace-nowrap border border-transparent px-3 py-2 font-mono text-xs uppercase tracking-wider text-muted-foreground transition-colors hover:border-border hover:bg-secondary hover:text-foreground data-[status=active]:border-ink data-[status=active]:bg-ink data-[status=active]:font-medium data-[status=active]:text-ink-foreground"
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
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 rounded-sm border border-ink/15 bg-frost px-4 py-3">
      <div>
        <h1 className="font-mono text-2xl font-medium uppercase tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("rounded-sm border border-ink/20 bg-card shadow-soft", className)}>{children}</div>;
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: "danger" }) {
  return (
    <div className="px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("mt-2 font-mono text-3xl text-ink", tone === "danger" && "text-destructive")}>{value}</p>
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
  return <span className={cn("inline-flex items-center rounded-sm border border-current/15 px-2 py-0.5 font-mono text-[11px] uppercase tracking-wider", tones[tone])}>{children}</span>;
}

export function EventBadge({ kind }: { kind: EventKind }) {
  return <Badge tone={isBlockedKind(kind) ? "danger" : kind === "handshake" ? "neutral" : "ok"}>{kind}</Badge>;
}

export function DataTable<T>({ columns, rows, rowKey, rowClass, empty, onRowClick }: {
  columns: { header: string; cell: (r: T) => ReactNode; className?: string }[];
  rows: T[];
  rowKey: (r: T) => string;
  rowClass?: (r: T) => string;
  empty?: ReactNode;
  onRowClick?: (r: T) => void;
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
            <tr
              key={rowKey(r)}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={cn("border-b last:border-0 transition-colors hover:bg-muted/50", onRowClick && "cursor-pointer", rowClass?.(r))}
            >
              {columns.map((c) => <td key={c.header} className={cn("px-5 py-3", c.className)}>{c.cell(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AuthCard({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-ink p-12 text-ink-foreground lg:flex">
        <div className="pointer-events-none absolute inset-0 bg-wash-ink" aria-hidden />
        <Brand className="relative text-ink-foreground [&_span]:border-ink-foreground [&_span]:bg-ink-foreground [&_span]:text-ink" />
        <div className="animate-rise relative max-w-md bg-frost-ink px-6 py-7">
          <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-ink-foreground/70">Permissioned agent runtime</p>
          <h2 className="mt-4 font-mono text-4xl leading-[1.1] text-ink-foreground">Decide what AI agents can see on your site.</h2>
          <p className="mt-5 text-sm leading-relaxed text-ink-foreground/80">
            Aurif is a control layer for AI traffic. Handshake, scoped JSON, redaction, audit — not a storefront chatbot.
          </p>
        </div>
        <p className="relative inline-flex w-fit bg-frost-ink px-3 py-2 font-mono text-xs tracking-wide text-ink-foreground/80">
          agent → handshake → scoped access → audit
        </p>
      </div>
      <div className="flex items-center justify-center bg-background bg-wash p-6">
        <div className="animate-rise w-full max-w-sm border border-ink/15 bg-frost px-6 py-8">
          <Brand className="mb-8 text-2xl lg:hidden" />
          <h1 className="font-mono text-3xl text-ink">{title}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">{subtitle}</p>
          <div className="mt-8">{children}</div>
          <div className="mt-6 text-sm text-muted-foreground">{footer}</div>
        </div>
      </div>
    </div>
  );
}

export const shortKey = (k: string) => `${k.slice(0, 12)}…${k.slice(-4)}`;
