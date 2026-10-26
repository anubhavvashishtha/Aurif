import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, shortKey } from "@/components/aurif/ui";
import { isBlockedKind, useActiveSite } from "@/lib/aurif-store";

export const Route = createFileRoute("/dashboard/")({ component: Overview });

function Overview() {
  const site = useActiveSite();
  const ev = site.events;
  const agents = new Set(ev.map((e) => e.agentId)).size;
  const open = site.endpoints.filter((e) => e.agentAccess).length;
  return (
    <>
      <PageHeader
        title="Overview"
        description="Toggle endpoints or change the welcome message to change what agents see."
      />
      <Panel className="grid grid-cols-2 divide-x divide-y sm:grid-cols-3 lg:grid-cols-5 lg:divide-y-0">
        <Stat label="Agents seen" value={agents} />
        <Stat label="Page reads" value={ev.filter((e) => e.kind === "page").length} />
        <Stat label="Actions" value={ev.filter((e) => e.kind === "action").length} />
        <Stat label="Blocked" value={ev.filter((e) => isBlockedKind(e.kind)).length} tone="danger" />
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
