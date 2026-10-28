import { createFileRoute } from "@tanstack/react-router";
import { RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { DataTable, EventBadge, PageHeader, Panel } from "@/components/aurif/ui";
import {
  isBlockedKind,
  refreshActivity,
  summarizeActivity,
  updateSite,
  useActiveSite,
  type AgentEvent,
} from "@/lib/aurif-store";
import { aurifHead } from "@/lib/aurif-meta";

export const Route = createFileRoute("/dashboard/activity")({ head: () => aurifHead("Agent activity", "Audit every agent handshake, read, action, block and redaction."), component: Activity });

function Activity() {
  const site = useActiveSite();
  const [spin, setSpin] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [aiSummary, setAiSummary] = useState<{
    summary: string;
    risks: string[];
    suggested_blocked_agents: string[];
    model?: string;
  } | null>(null);
  const rows = [...site.events].sort((a, b) => b.time.localeCompare(a.time));

  const runSummary = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await summarizeActivity(site.id);
      setAiSummary({ ...res.summary, model: res.model });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Summary failed");
    } finally {
      setBusy(false);
    }
  };

  const applyBlocks = async () => {
    if (!aiSummary?.suggested_blocked_agents?.length) return;
    const existing = site.blockedAgents
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const merged = [...new Set([...existing, ...aiSummary.suggested_blocked_agents])];
    await updateSite(site.id, { blockedAgents: merged.join(", ") });
  };

  return (
    <>
      <PageHeader
        title="Agent activity"
        description="Every handshake, page read and action from AI agents, newest first."
        action={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => void runSummary()}
            >
              <Sparkles /> {busy ? "Summarizing…" : "Muse summary"}
            </Button>
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
          </div>
        }
      />
      {error && <p className="mb-3 text-sm text-destructive">{error}</p>}
      {aiSummary && (
        <Panel className="mb-4 space-y-2 border-ink/15 bg-frost p-5">
          <p className="text-sm text-ink">{aiSummary.summary}</p>
          {!!aiSummary.risks?.length && (
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {aiSummary.risks.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          {!!aiSummary.suggested_blocked_agents?.length && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs">
                Suggest block: {aiSummary.suggested_blocked_agents.join(", ")}
              </span>
              <Button size="sm" variant="outline" onClick={() => void applyBlocks()}>
                Apply blocks
              </Button>
            </div>
          )}
          {aiSummary.model && (
            <p className="text-xs text-muted-foreground">Model: {aiSummary.model}</p>
          )}
        </Panel>
      )}
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
            { header: "URL / action_id", cell: (r) => <span className="font-mono text-xs text-muted-foreground">{r.target}{r.redactedFields?.length ? <span className="ml-2 rounded-sm border border-ink bg-ink px-2 py-0.5 text-ink-foreground">redacted: {r.redactedFields.join(", ")}</span> : null}</span> },
          ]}
        />
      </Panel>
    </>
  );
}
