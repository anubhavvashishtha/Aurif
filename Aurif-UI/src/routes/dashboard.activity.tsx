import { createFileRoute } from "@tanstack/react-router";
import { RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge, DataTable, EventBadge, PageHeader, Panel } from "@/components/aurif/ui";
import { MetaCredit } from "@/components/aurif/meta-credit";
import {
  isBlockedKind,
  refreshActivity,
  summarizeActivity,
  useActiveSite,
  type AgentEvent,
  type MetaFeatureResponse,
} from "@/lib/aurif-store";
import { aurifHead } from "@/lib/aurif-meta";
import { riskTone } from "@/lib/meta-risk";

export const Route = createFileRoute("/dashboard/activity")({ head: () => aurifHead("Agent activity", "Audit every agent handshake, read, action, block and redaction."), component: Activity });

function Activity() {
  const site = useActiveSite();
  useEffect(() => {
    if (!site?.id) return;
    void refreshActivity(site.id).catch(() => undefined);
  }, [site?.id]);
  const [spin, setSpin] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [aiSummary, setAiSummary] = useState<{
    summary: string;
    risks: string[];
    suggested?: string[];
    meta: MetaFeatureResponse;
  } | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const rows = [...site.events].sort((a, b) => b.time.localeCompare(a.time));
  const open = rows.find((r) => r.id === openId) || null;

  const runSummary = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await summarizeActivity(site.id);
      setAiSummary({
        summary: res.summary.summary,
        risks: res.summary.risks || [],
        suggested: res.summary.suggested_blocked_agents || [],
        meta: {
          model: res.model,
          model_info: res.model_info || (typeof res.summary.model === "object" ? res.summary.model : undefined),
          latency_ms: res.latency_ms ?? res.summary.latency_ms,
          source: res.source || res.summary.source,
          degraded: res.degraded ?? res.summary.degraded,
          fallback: res.fallback ?? res.summary.fallback,
          warning: res.warning || res.summary.warning,
        },
      });
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
              <Sparkles /> {busy ? "Summarizing…" : "Summarize with Meta"}
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
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-mono text-sm uppercase tracking-wider text-ink">Activity summary</h2>
            {aiSummary.meta.degraded ? (
              <Badge tone="danger">Fallback</Badge>
            ) : aiSummary.meta.fallback ? (
              <Badge tone="muted">Fallback</Badge>
            ) : null}
          </div>
          <p className="text-sm text-ink">{aiSummary.summary}</p>
          {!!aiSummary.risks?.length && (
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {aiSummary.risks.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          {!!aiSummary.suggested?.length && (
            <p className="text-sm text-muted-foreground">Suggested blocks: {aiSummary.suggested.join(", ")}</p>
          )}
          <MetaCredit
            model={aiSummary.meta.model_info || aiSummary.meta.model}
            latencyMs={aiSummary.meta.latency_ms}
            degraded={aiSummary.meta.degraded}
            fallback={aiSummary.meta.fallback}
            warning={aiSummary.meta.warning}
          />
        </Panel>
      )}
      <HandshakeRiskList rows={rows} />
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
            {
              header: "Risk",
              cell: (r) =>
                r.purposeRisk ? (
                  <span className="inline-flex items-center gap-1">
                    <Badge tone={riskTone(r.purposeRisk.risk)}>{r.purposeRisk.risk}</Badge>
                    {r.purposeRisk.degraded && <Badge tone="danger">Fallback</Badge>}
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                ),
            },
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
            {open.purposeRisk && (
              <div className="mt-3 space-y-1">
                <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Handshake risk</p>
                <p className="text-sm text-ink">{open.purposeRisk.reason || "No rationale recorded."}</p>
                <MetaCredit
                  model={open.purposeRisk.model}
                  latencyMs={open.purposeRisk.latencyMs}
                  degraded={open.purposeRisk.degraded}
                  fallback={open.purposeRisk.fallback}
                  warning={open.purposeRisk.warning}
                />
              </div>
            )}
          </div>
        )}
      </Panel>
    </>
  );
}

function HandshakeRiskList({ rows }: { rows: AgentEvent[] }) {
  const scored = rows.filter((row) => row.kind === "handshake" && row.purposeRisk).slice(0, 5);
  if (!scored.length) return null;
  return (
    <Panel className="mb-4 divide-y">
      <div className="px-5 py-3">
        <h2 className="font-mono text-sm uppercase tracking-wider text-ink">Handshake risk</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Each handshake is scored before scopes are granted. A fallback score is labelled and still limits act.
        </p>
      </div>
      {scored.map((row) => (
        <div key={row.id} className="space-y-1 px-5 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs">{row.agentId}</span>
            <Badge tone={riskTone(row.purposeRisk!.risk)}>{row.purposeRisk!.risk}</Badge>
            {row.purposeRisk!.degraded && <Badge tone="danger">Fallback</Badge>}
            {!!row.grantedScopes?.length && (
              <span className="font-mono text-[11px] text-muted-foreground">{row.grantedScopes.join(", ")}</span>
            )}
          </div>
          {row.purpose && <p className="text-sm text-ink">{row.purpose}</p>}
          <p className="text-sm text-muted-foreground">{row.purposeRisk!.reason}</p>
          <MetaCredit
            model={row.purposeRisk!.model}
            latencyMs={row.purposeRisk!.latencyMs}
            degraded={row.purposeRisk!.degraded}
            fallback={row.purposeRisk!.fallback}
            warning={row.purposeRisk!.warning}
          />
        </div>
      ))}
    </Panel>
  );
}
