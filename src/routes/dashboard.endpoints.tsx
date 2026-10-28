import { createFileRoute } from "@tanstack/react-router";
import { SlidersHorizontal, Sparkles } from "lucide-react";
import { useState } from "react";
import { Badge, PageHeader, Panel } from "@/components/aurif/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { agentResponse, filterRequest } from "@/lib/aurif-fields";
import { aurifHead } from "@/lib/aurif-meta";
import {
  applyPolicy,
  proposePolicy,
  toggleEndpoint,
  updateRequestField,
  updateResponseFields,
  useActiveSite,
  type Endpoint,
} from "@/lib/aurif-store";

export const Route = createFileRoute("/dashboard/endpoints")({
  head: () => aurifHead("Endpoint control", "Allow AI endpoints and choose which JSON fields agents receive."),
  component: Endpoints,
});

const DIRECTION = { read: "Returns JSON", write: "Accepts JSON", both: "Both" };

function PolicyCopilot({ siteId }: { siteId: string }) {
  const [instruction, setInstruction] = useState("Hide prices from agents and disable checkout");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [proposal, setProposal] = useState<{
    summary: string;
    patches: Array<Record<string, unknown>>;
    blocked_agents_add?: string[];
    model?: string;
  } | null>(null);

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await proposePolicy(siteId, instruction);
      setProposal({ ...res.proposal, model: res.model });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Propose failed");
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!proposal) return;
    setBusy(true);
    setError("");
    try {
      await applyPolicy(siteId, proposal.patches, proposal.blocked_agents_add || []);
      setProposal(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Apply failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel className="mb-6 space-y-3 border-ink/15 bg-frost p-5">
      <div className="flex items-center gap-2">
        <Sparkles className="size-4 text-accent" />
        <h2 className="text-lg text-ink">Muse policy co-pilot</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Describe policy in plain English. Muse Spark Open proposes endpoint patches — you confirm before apply.
      </p>
      <div className="space-y-1.5">
        <Label>Instruction</Label>
        <Input value={instruction} onChange={(e) => setInstruction(e.target.value)} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || !instruction.trim()} onClick={() => void run()}>
          {busy ? "Thinking…" : "Propose with Muse"}
        </Button>
        {proposal && (
          <Button variant="outline" disabled={busy} onClick={() => void apply()}>
            Apply proposal
          </Button>
        )}
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {proposal && (
        <pre className="max-h-64 overflow-auto rounded-lg bg-ink p-4 font-mono text-xs text-ink-foreground">
          {JSON.stringify(proposal, null, 2)}
        </pre>
      )}
    </Panel>
  );
}

function Endpoints() {
  const site = useActiveSite();
  const [openId, setOpenId] = useState<string | null>(null);
  const open = site.endpoints.find((e) => e.id === openId);
  return (
    <>
      <PageHeader title="Endpoint control" description="Agents can use the endpoint, but only the fields you allow. Turning an endpoint off blocks agents with 403." />
      <PolicyCopilot siteId={site.id} />
      {["page", "action"].map((kind) => (
        <section key={kind} className="mb-6">
          <h2 className="mb-2 inline-block rounded-sm border border-ink/15 bg-frost px-2 py-0.5 font-mono text-sm uppercase tracking-wider text-ink">{kind}s</h2>
          <Panel className="divide-y">
            {site.endpoints.filter((e) => e.kind === kind).map((e) => {
              const hidden = e.responseFields.filter((f) => !f.agentVisible).length;
              return (
                <div key={e.id} className="flex flex-wrap items-center gap-3 px-5 py-3.5">
                  <div className="min-w-48 flex-1"><p className="font-medium">{e.label}</p><p className="font-mono text-xs text-muted-foreground">{e.ref}</p></div>
                  <Badge tone="muted">{e.kind}</Badge><Badge>{DIRECTION[e.direction]}</Badge>
                  {hidden > 0 && <Badge tone="danger">{hidden} hidden</Badge>}
                  <Button size="sm" variant={e.agentAccess ? "outline" : "ghost"} disabled={!e.agentAccess} onClick={() => setOpenId(e.id)}><SlidersHorizontal /> Configure fields</Button>
                  <Switch checked={e.agentAccess} onCheckedChange={(v) => toggleEndpoint(site.id, e.id, v)} aria-label={`Agent access for ${e.label}`} />
                </div>
              );
            })}
          </Panel>
        </section>
      ))}
      <Sheet open={!!open} onOpenChange={(v) => !v && setOpenId(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-4xl">{open && <FieldDrawer siteId={site.id} endpoint={open} />}</SheetContent>
      </Sheet>
    </>
  );
}

function FieldDrawer({ siteId, endpoint: e }: { siteId: string; endpoint: Endpoint }) {
  const hidden = e.responseFields.filter((f) => !f.agentVisible).length;
  return (
    <div className="space-y-5">
      <SheetHeader className="pr-8">
        <div className="flex items-center justify-between gap-4"><SheetTitle className="font-mono text-xl uppercase tracking-tight text-ink">{e.label}</SheetTitle><Switch checked={e.agentAccess} onCheckedChange={(v) => toggleEndpoint(siteId, e.id, v)} aria-label="Agent access" /></div>
        <SheetDescription>If access is on but price is hidden, agents still get JSON — without the price field.</SheetDescription>
      </SheetHeader>
      <Tabs defaultValue={e.direction === "write" ? "request" : "response"}>
        <TabsList>{e.direction !== "write" && <TabsTrigger value="response">Response JSON</TabsTrigger>}{e.direction !== "read" && <TabsTrigger value="request">Request JSON</TabsTrigger>}</TabsList>
        <TabsContent value="response" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm text-muted-foreground">{hidden ? `${hidden} fields omitted from agent responses.` : "All fields are visible to agents."}</p>
            <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => updateResponseFields(siteId, e.id, (fs) => fs.map((f) => /price/.test(f.key) ? { ...f, agentVisible: false } : f))}>Hide all prices</Button><Button size="sm" variant="ghost" onClick={() => updateResponseFields(siteId, e.id, (fs) => fs.map((f) => ({ ...f, agentVisible: true })))}>Show all</Button></div></div>
          <Panel className="divide-y">{e.responseFields.map((f) => <div key={f.key} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 px-4 py-2.5"><div><p className="font-mono text-xs">{f.key}</p><p className="text-xs text-muted-foreground">{f.label}</p></div><Badge tone="muted">{f.type}</Badge><Switch checked={f.agentVisible} onCheckedChange={(v) => updateResponseFields(siteId, e.id, (fs) => fs.map((x) => x.key === f.key ? { ...x, agentVisible: v } : x))} aria-label={`Visible to agents: ${f.key}`} /></div>)}</Panel>
          <JsonSplit left={e.sampleResponse} right={agentResponse(e, e.sampleResponse).body} rightTitle="What the agent receives" />
        </TabsContent>
        <TabsContent value="request" className="space-y-4">
          <p className="text-sm text-muted-foreground">Disallowed fields are ignored on receive.</p>
          <Panel className="divide-y">{e.requestFields.map((f) => <div key={f.key} className="flex items-center gap-3 px-4 py-2.5"><div className="flex-1"><p className="font-mono text-xs">{f.key}</p><p className="text-xs text-muted-foreground">{f.label}</p></div><Switch checked={f.agentAllowed} onCheckedChange={(v) => updateRequestField(siteId, e.id, f.key, v)} aria-label={`Agent may send ${f.key}`} /></div>)}</Panel>
          <JsonSplit left={e.sampleRequest} right={filterRequest(e.sampleRequest, e.requestFields)} rightTitle="What Aurif accepts" />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function JsonSplit({ left, right, rightTitle }: { left: unknown; right: unknown; rightTitle: string }) {
  return <div className="grid gap-3 md:grid-cols-2">{[["Full JSON (owner view)", left], [rightTitle, right]].map(([t, v]) => <div key={t as string}><p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">{t as string}</p><pre className="max-h-96 overflow-auto rounded-lg bg-ink p-4 font-mono text-xs text-ink-foreground">{JSON.stringify(v, null, 2)}</pre></div>)}</div>;
}