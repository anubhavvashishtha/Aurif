import { createFileRoute } from "@tanstack/react-router";
import { RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { DataTable, EventBadge, PageHeader, Panel } from "@/components/aurif/ui";
import {
  isBlockedKind,
  refreshActivity,
  summarizeActivity,
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
    model?: string;
  } | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const rows = [...site.events].sort((a, b) => b.time.localeCompare(a.time));
  const open = rows.find((r) => r.id === openId) || null;

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

  return (
    <>
      <PageHeader
        title="Agent activity"
        description="Click a row to see what the request asked for and where it went. A matching site key is what gets accepted."
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
          {aiSummary.model && (
            <p className="text-xs text-muted-foreground">Model: {aiSummary.model}</p>
          )}
        </Panel>
      )}
      <Panel>
        <DataTable<AgentEvent>
          rows={rows}
          rowKey={(r) => r.id}
          onRowClick={(r) => setOpenId((id) => (id === r.id ? null : r.id))}
          rowClass={(r) => (openId === r.id ? "bg-secondary" : isBlockedKind(r.kind) || r.accepted === false ? "bg-danger-soft/40" : "")}
          empty="No agent activity yet. Ask Muse to try the site."
          columns={[
            { header: "Time", cell: (r) => <span className="whitespace-nowrap font-mono text-xs text-muted-foreground">{new Date(r.time).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span> },
            { header: "Result", cell: (r) => <span className="font-mono text-xs uppercase">{r.accepted === false || isBlockedKind(r.kind) ? "Denied" : r.accepted ? "Accepted" : "Logged"}</span> },
            { header: "Event", cell: (r) => <EventBadge kind={r.kind} /> },
            { header: "Asked", cell: (r) => <span className="font-mono text-xs text-muted-foreground">{r.target}</span> },
          ]}
        />
        {open && (
          <div className="border-t border-ink/10 px-5 py-4 text-sm">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Request</p>
            <p className="mt-1 text-ink">{open.reason || "No reason recorded."}</p>
            <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Asked</p>
            <pre className="mt-1 overflow-auto border border-ink/10 bg-frost p-3 font-mono text-xs text-ink">{JSON.stringify(open.asked ?? open.target, null, 2)}</pre>
            <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Navigated</p>
            <p className="mt-1 font-mono text-xs">{open.navigated?.length ? open.navigated.join(" → ") : "Did not navigate."}</p>
          </div>
        )}
      </Panel>
    </>
  );
}
