import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect } from "react";
import { PageHeader, Panel, Stat, shortKey, Badge } from "@/components/aurif/ui";
import { MetaCredit } from "@/components/aurif/meta-credit";
import { isBlockedKind, refreshActivity, useActiveSite } from "@/lib/aurif-store";
import { aurifHead } from "@/lib/aurif-meta";
import { riskTone } from "@/lib/meta-risk";

export const Route = createFileRoute("/dashboard/")({ head: () => aurifHead("Overview", "See AI agent reads, actions, blocks and field redactions."), component: Overview });

function Overview() {
  const site = useActiveSite();
  const ev = site.events;
  useEffect(() => {
    if (!site?.id) return;
    void refreshActivity(site.id).catch(() => undefined);
  }, [site?.id]);
  const agents = new Set(ev.map((e) => e.agentId)).size;
  const open = site.endpoints.filter((e) => e.agentAccess).length;
  const latestHandshake = [...ev]
    .filter((event) => event.kind === "handshake" && event.purposeRisk)
    .sort((a, b) => b.time.localeCompare(a.time))[0];
  const risk = latestHandshake?.purposeRisk;
  return (
    <>
      <PageHeader
        title="Overview"
        description="A Meta model scores each handshake, drafts policy changes, and summarizes agent activity. You still decide what gets applied."
      />
      <Panel className="mb-6 space-y-3 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-mono text-sm uppercase tracking-wider text-ink">Latest handshake risk</h2>
          {risk && <Badge tone={riskTone(risk.risk)}>{risk.risk}</Badge>}
          {risk?.degraded && <Badge tone="danger">Fallback</Badge>}
        </div>
        {latestHandshake && risk ? (
          <>
            <p className="text-sm text-ink">
              <span className="font-mono">{latestHandshake.agentId}</span>
              {latestHandshake.purpose ? ` — ${latestHandshake.purpose}` : ""}
            </p>
            <p className="text-sm text-muted-foreground">{risk.reason || "No rationale recorded."}</p>
            {!!latestHandshake.grantedScopes?.length && (
              <p className="font-mono text-xs text-muted-foreground">
                Granted {latestHandshake.grantedScopes.join(", ")}
                {risk.dropAct ? " · act withheld" : ""}
              </p>
            )}
            <MetaCredit
              model={risk.model}
              latencyMs={risk.latencyMs}
              degraded={risk.degraded}
              fallback={risk.fallback}
              warning={risk.warning}
            />
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            No scored handshake yet. When an agent connects, the score, rationale, and model show up here and on{" "}
            <Link to="/dashboard/activity" className="underline">
              Agent activity
            </Link>
            .
          </p>
        )}
      </Panel>
      <Panel className="grid grid-cols-2 divide-x divide-y sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
        <Stat label="Agents seen" value={agents} />
        <Stat label="Page reads" value={ev.filter((e) => e.kind === "page").length} />
        <Stat label="Actions" value={ev.filter((e) => e.kind === "action").length} />
        <Stat label="Blocked" value={ev.filter((e) => isBlockedKind(e.kind)).length} tone="danger" />
        <Stat label="Redacted" value={ev.filter((e) => e.kind === "field_redacted").length} />
        <Stat label="Endpoints open" value={<>{open}<span className="text-lg text-muted-foreground"> / {site.endpoints.length}</span></>} />
      </Panel>
      <Panel className="mt-6 divide-y">
        {[
          ["Site name", site.name],
          ["URL", site.url],
          ["Site key", <span className="font-mono text-xs">{shortKey(site.siteKey)}</span>],
        ].map(([k, v]) => (
          <div key={k as string} className="flex justify-between gap-4 px-5 py-3.5 text-sm">
            <span className="text-muted-foreground">{k}</span>
            <span className="truncate text-foreground">{v}</span>
          </div>
        ))}
      </Panel>
    </>
  );
}
