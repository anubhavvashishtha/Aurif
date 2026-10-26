import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, ExternalLink, Info } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CUSTOMER_SITE_URL, Panel, SiteSwitcher, Topbar } from "@/components/aurif/ui";
import { getState, logEvent, useActiveSite } from "@/lib/aurif-store";

export const Route = createFileRoute("/console")({
  head: () => ({
    meta: [
      { title: "Agent console — Aurif" },
      { name: "description", content: "Simulate a third-party AI agent against your site's Aurif endpoints." },
      { property: "og:title", content: "Agent console — Aurif" },
      { property: "og:description", content: "Test how AI agents see your site through Aurif." },
    ],
  }),
  ssr: false,
  component: Console,
});

function Console() {
  const site = useActiveSite();
  const [agentId, setAgentId] = useState("test-agent/1.0");
  const [scopes, setScopes] = useState("view");
  const [purpose, setPurpose] = useState("Summarize product catalog");
  const [key, setKey] = useState("");
  const [path, setPath] = useState("/products");
  const [log, setLog] = useState<string[]>([]);

  const push = (label: string, body: unknown) =>
    setLog((l) => [`// ${new Date().toLocaleTimeString()}  ${label}\n${JSON.stringify(body, null, 2)}`, ...l]);

  // API hooks (agent): GET /.well-known/aurif, POST /aurif/handshake, GET /aurif/page, POST /aurif/action, GET /aurif/audit
  const blocked = () => site.blockedAgents.split(",").map((s) => s.trim()).filter(Boolean).includes(agentId);
  const badKey = () => key !== "" && key !== site.siteKey;

  const run = {
    discover: () => push("GET /.well-known/aurif", {
      site: site.name, version: "1",
      endpoints: site.endpoints.filter((e) => e.agentAccess).map((e) => ({ kind: e.kind, ref: e.ref })),
    }),
    handshake: () => {
      if (blocked() || badKey()) {
        logEvent(site.id, { agentId, kind: "handshake_denied", target: blocked() ? "agent blocked by owner" : "invalid site key" });
        return push("POST /aurif/handshake → 403", { error: blocked() ? "agent_blocked" : "invalid_site_key" });
      }
      logEvent(site.id, { agentId, kind: "handshake", target: `scopes=${scopes}` });
      push("POST /aurif/handshake → 200", { agent_id: agentId, scopes: scopes.split("+"), purpose, token: "agt_" + crypto.randomUUID().slice(0, 8) });
    },
    page: () => {
      const ep = site.endpoints.find((e) => e.kind === "page" && (e.ref === path || (e.ref.includes(":") && path.startsWith(e.ref.split(":")[0]))));
      if (!ep || !ep.agentAccess) {
        logEvent(site.id, { agentId, kind: "page_blocked", target: path });
        return push(`GET /aurif/page?path=${path} → 403`, { error: "agent_access_off" });
      }
      logEvent(site.id, { agentId, kind: "page", target: path });
      push(`GET /aurif/page?path=${path} → 200`, { title: ep.label, summary: site.welcome, path });
    },
    action: () => {
      const ep = site.endpoints.find((e) => e.ref === "cart.add.field_tote")!;
      if (scopes !== "view+act" || !ep.agentAccess) {
        logEvent(site.id, { agentId, kind: "action_blocked", target: ep.ref });
        return push(`POST /aurif/action ${ep.ref} → 403`, { error: scopes !== "view+act" ? "scope_missing" : "agent_access_off" });
      }
      logEvent(site.id, { agentId, kind: "action", target: ep.ref });
      push(`POST /aurif/action ${ep.ref} → 200`, { ok: true, cart_items: 1 });
    },
    audit: () => {
      const s = getState().sites.find((x) => x.id === site.id)!;
      push("GET /aurif/audit", s.events.filter((e) => e.agentId === agentId).slice(0, 10));
    },
  };

  return (
    <div className="min-h-screen bg-background bg-wash">
      <Topbar label="Agent console" />
      <main className="animate-rise mx-auto max-w-7xl px-4 py-8 md:px-6">
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <Button variant="ghost" size="sm" asChild><Link to="/dashboard"><ArrowLeft /> Dashboard</Link></Button>
          <Button variant="ghost" size="sm" asChild><a href={CUSTOMER_SITE_URL} target="_blank" rel="noreferrer">Open customer site <ExternalLink /></a></Button>
        </div>
        <h1 className="text-3xl text-ink">Agent console</h1>
        <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-primary/30 bg-accent px-4 py-3 text-sm text-accent-foreground">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          Aurif product tool — talks only to AI endpoints. No vision/mouse clicking on the human UI.
        </div>
        <div className="mt-6 grid gap-6 lg:grid-cols-[360px_1fr]">
          <Panel className="space-y-4 self-start p-5">
            <div className="space-y-1.5"><Label>Target site</Label><SiteSwitcher /></div>
            <div className="space-y-1.5"><Label>Agent ID</Label><Input className="font-mono text-xs" value={agentId} onChange={(e) => setAgentId(e.target.value)} /></div>
            <div className="space-y-1.5">
              <Label>Scopes</Label>
              <Select value={scopes} onValueChange={setScopes}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="view">view</SelectItem><SelectItem value="view+act">view + act</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Purpose</Label><Input value={purpose} onChange={(e) => setPurpose(e.target.value)} /></div>
            <div className="space-y-1.5"><Label>Site key (optional)</Label><Input className="font-mono text-xs" placeholder="ak_live_…" value={key} onChange={(e) => setKey(e.target.value)} /></div>
            <div className="space-y-1.5"><Label>Page path</Label><Input className="font-mono text-xs" value={path} onChange={(e) => setPath(e.target.value)} /></div>
            <div className="grid grid-cols-2 gap-2 pt-2">
              <Button variant="outline" onClick={run.discover}>Discover</Button>
              <Button onClick={run.handshake}>Handshake</Button>
              <Button variant="outline" onClick={run.page}>Get page</Button>
              <Button variant="outline" onClick={run.action}>Run sample action</Button>
              <Button variant="secondary" className="col-span-2" onClick={run.audit}>Audit</Button>
            </div>
          </Panel>
          <Panel className="flex min-h-[480px] flex-col overflow-hidden">
            <div className="flex items-center justify-between border-b px-5 py-3">
              <span className="text-sm font-medium">Response log</span>
              <Button variant="ghost" size="sm" onClick={() => setLog([])}>Clear</Button>
            </div>
            <pre className="flex-1 overflow-auto bg-ink p-5 font-mono text-xs leading-relaxed text-ink-foreground">
              {log.length ? log.join("\n\n") : "// Run Discover or Handshake to begin."}
            </pre>
          </Panel>
        </div>
      </main>
    </div>
  );
}
