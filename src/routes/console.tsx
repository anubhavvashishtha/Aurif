import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, ExternalLink, Info } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CUSTOMER_SITE_URL, Panel, SiteSwitcher, Topbar } from "@/components/aurif/ui";
import { API_BASE } from "@/lib/api";
import { refreshActivity, useActiveSite } from "@/lib/aurif-store";

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
  const [agentId, setAgentId] = useState("third-party-agent");
  const [scopes, setScopes] = useState("view+act");
  const [purpose, setPurpose] = useState("Help user browse Northline and add one item");
  const [key, setKey] = useState("");
  const [path, setPath] = useState("/products/field-tote");
  const [session, setSession] = useState("");
  const [log, setLog] = useState<string[]>([]);

  const push = (label: string, body: unknown) =>
    setLog((l) => [`// ${new Date().toLocaleTimeString()}  ${label}\n${JSON.stringify(body, null, 2)}`, ...l]);

  const agentFetch = async (p: string, init?: RequestInit) => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Aurif-Protocol": "aurif-1",
      ...(init?.headers as Record<string, string> | undefined),
    };
    if (session) headers["X-Aurif-Session"] = session;
    if (key) headers["X-Aurif-Site-Key"] = key;
    const res = await fetch(API_BASE + p, { ...init, headers });
    const data = await res.json().catch(() => ({}));
    return { res, data };
  };

  const run = {
    discover: async () => {
      const { res, data } = await agentFetch("/.well-known/aurif.json");
      push(`GET /.well-known/aurif.json → ${res.status}`, data);
    },
    handshake: async () => {
      const requested = scopes.split("+").map((s) => s.trim()).filter(Boolean);
      const { res, data } = await agentFetch("/ai/handshake", {
        method: "POST",
        body: JSON.stringify({
          agent_id: agentId,
          agent_version: "1.0",
          requested_scopes: requested,
          purpose,
          ...(key ? { site_key: key } : {}),
        }),
      });
      if (data.session_token) setSession(data.session_token);
      push(`POST /ai/handshake → ${res.status}`, data);
      await refreshActivity(site.id).catch(() => undefined);
    },
    page: async () => {
      const { res, data } = await agentFetch(`/ai/page?path=${encodeURIComponent(path)}`);
      push(`GET /ai/page?path=${path} → ${res.status}`, data);
      await refreshActivity(site.id).catch(() => undefined);
    },
    action: async () => {
      const { res, data } = await agentFetch("/ai/actions", {
        method: "POST",
        body: JSON.stringify({ action_id: "product.add:field-tote", args: {} }),
      });
      push(`POST /ai/actions product.add:field-tote → ${res.status}`, data);
      await refreshActivity(site.id).catch(() => undefined);
    },
    audit: async () => {
      const { res, data } = await agentFetch("/ai/audit");
      push(`GET /ai/audit → ${res.status}`, data);
    },
  };

  return (
    <div className="min-h-screen bg-background bg-wash">
      <Topbar />
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 md:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" asChild>
              <Link to="/dashboard">
                <ArrowLeft /> Back
              </Link>
            </Button>
            <SiteSwitcher />
          </div>
          <Button variant="ghost" size="sm" asChild>
            <a href={CUSTOMER_SITE_URL} target="_blank" rel="noreferrer">
              Open customer site <ExternalLink />
            </a>
          </Button>
        </div>

        <Panel className="flex gap-3 border-accent/30 bg-accent-soft/40 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-accent" />
          <p>
            Aurif product tool — talks only to AI endpoints on <code className="font-mono text-xs">{API_BASE}</code>.
            No vision / mouse clicking on the customer UI.
          </p>
        </Panel>

        <div className="grid gap-6 lg:grid-cols-2">
          <Panel className="space-y-4 p-5">
            <div className="space-y-1.5">
              <Label>Agent id</Label>
              <Input className="font-mono text-xs" value={agentId} onChange={(e) => setAgentId(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Scopes</Label>
              <Select value={scopes} onValueChange={setScopes}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="view">view</SelectItem>
                  <SelectItem value="view+act">view+act</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Purpose</Label>
              <Input value={purpose} onChange={(e) => setPurpose(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Site key (optional)</Label>
              <Input className="font-mono text-xs" value={key} onChange={(e) => setKey(e.target.value)} placeholder={site?.siteKey?.slice(0, 8) + "…"} />
            </div>
            <div className="space-y-1.5">
              <Label>Page path</Label>
              <Input className="font-mono text-xs" value={path} onChange={(e) => setPath(e.target.value)} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void run.discover()}>Discover</Button>
              <Button onClick={() => void run.handshake()}>Handshake</Button>
              <Button variant="outline" onClick={() => void run.page()}>
                Get page
              </Button>
              <Button variant="outline" onClick={() => void run.action()}>
                Add Field Tote
              </Button>
              <Button variant="ghost" onClick={() => void run.audit()}>
                Audit
              </Button>
            </div>
          </Panel>
          <Panel className="p-0">
            <pre className="max-h-[640px] overflow-auto p-4 font-mono text-xs leading-relaxed text-muted-foreground">
              {log.length ? log.join("\n\n") : "// Response log"}
            </pre>
          </Panel>
        </div>
      </div>
    </div>
  );
}
