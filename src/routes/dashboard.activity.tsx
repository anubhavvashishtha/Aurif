import { createFileRoute } from "@tanstack/react-router";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { DataTable, EventBadge, PageHeader, Panel } from "@/components/aurif/ui";
import { isBlockedKind, refreshActivity, useActiveSite, type AgentEvent } from "@/lib/aurif-store";
import { aurifHead } from "@/lib/aurif-meta";

export const Route = createFileRoute("/dashboard/activity")({ head: () => aurifHead("Agent activity", "Audit every agent handshake, read, action, block and redaction."), component: Activity });

function Activity() {
  const site = useActiveSite();
  const [spin, setSpin] = useState(false);
  const rows = [...site.events].sort((a, b) => b.time.localeCompare(a.time));
  return (
    <>
      <PageHeader
        title="Agent activity"
        description="Every handshake, page read and action from AI agents, newest first."
        action={
          // API hook (activity): GET /api/sites/:id/activity
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              setSpin(true);
              try {
                await refreshActivity(site.id);
              } finally {
                setSpin(false);
              }
            }}
          >
            <RefreshCw className={spin ? "animate-spin" : ""} /> Refresh
          </Button>
        }
      />
      <Panel>
        <DataTable<AgentEvent>
          rows={rows}
          rowKey={(r) => r.id}
          rowClass={(r) => (isBlockedKind(r.kind) ? "bg-danger-soft/40" : "")}
          empty="No agent activity yet. Run an agent against your site."
          columns={[
            { header: "Time", cell: (r) => <span className="whitespace-nowrap font-mono text-xs text-muted-foreground">{new Date(r.time).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span> },
            { header: "Agent ID", cell: (r) => <span className="font-mono text-xs">{r.agentId}</span> },
            { header: "Event", cell: (r) => <EventBadge kind={r.kind} /> },
            { header: "URL / action_id", cell: (r) => <span className="font-mono text-xs text-muted-foreground">{r.target}{r.redactedFields?.length ? <span className="ml-2 rounded-full bg-accent px-2 py-0.5 text-accent-foreground">redacted: {r.redactedFields.join(", ")}</span> : null}</span> },
          ]}
        />
      </Panel>
    </>
  );
}
