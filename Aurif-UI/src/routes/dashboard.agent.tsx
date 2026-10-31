import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageHeader, Panel } from "@/components/aurif/ui";
import {
  chatWithMuse,
  fetchAgentModels,
  refreshActivity,
  useActiveSite,
  type AgentModel,
} from "@/lib/aurif-store";
import { aurifHead } from "@/lib/aurif-meta";

export const Route = createFileRoute("/dashboard/agent")({
  head: () =>
    aurifHead("Agent dashboard", "Ask Muse a question about a page — pick a model and site-key mode."),
  component: AgentDashboard,
});

type ChatMessage = {
  id: string;
  role: "user" | "muse";
  text: string;
  denied?: boolean;
  modelLabel?: string;
};

function AgentDashboard() {
  const site = useActiveSite();
  const [useSiteKey, setUseSiteKey] = useState(false);
  const [models, setModels] = useState<AgentModel[]>([]);
  const [modelId, setModelId] = useState("");
  const [visionCredit, setVisionCredit] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "intro",
      role: "muse",
      text: "Hello, I am Muse. Send a link and ask a question — I'll summarize what happened and answer if I can get the data.",
    },
  ]);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchAgentModels();
        if (cancelled) return;
        const list = res.models || [];
        setModels(list);
        const current = res.current || list.find((m) => m.default) || list[0];
        if (current?.id) setModelId(current.id);
        const health = res.health;
        const vision = health?.vision;
        if (vision?.model) {
          const name = vision.powered_by || vision.label || vision.model;
          setVisionCredit(`Powered by ${name}`);
        } else {
          setVisionCredit(null);
        }
      } catch {
        /* keep empty; user can still chat with server default */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const selected = models.find((m) => m.id === modelId);

  const send = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text }]);
    setBusy(true);
    try {
      const res = await chatWithMuse({
        message: text,
        use_site_key: useSiteKey,
        site_key: useSiteKey ? site.siteKey : undefined,
        model: modelId || undefined,
      });
      const used =
        res.model?.label ||
        selected?.label ||
        res.model?.id ||
        modelId ||
        undefined;
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "muse",
          text: res.reply,
          denied: res.denied,
          modelLabel: used,
        },
      ]);
      await refreshActivity(site.id);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "muse",
          denied: true,
          text: err instanceof Error ? err.message : "Muse could not reach the site.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Agent dashboard"
        description="Ask Muse about a page. Pick a model, optionally send a site key, and get a short answer."
      />
      <Panel className="flex h-[calc(100vh-14rem)] min-h-[28rem] flex-col">
        <div className="grid grid-cols-1 gap-4 border-b border-ink/10 px-4 py-3 sm:grid-cols-2 sm:items-start">
          <div className="min-w-0">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Model</p>
            <div className="mt-1.5 flex h-9 items-center">
              <Select value={modelId || undefined} onValueChange={setModelId}>
                <SelectTrigger className="w-full" aria-label="Inference model">
                  <SelectValue placeholder="Select a model" />
                </SelectTrigger>
                <SelectContent>
                  {models.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.label} · {m.provider}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {selected ? `Text · ${selected.label} via ${selected.provider}` : "Text · server default model"}
            </p>
            {visionCredit && (
              <p className="mt-1 text-xs text-muted-foreground">CAPTCHA vision · {visionCredit}</p>
            )}
          </div>
          <div className="min-w-0">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Site key</p>
            <div className="mt-1.5 flex h-9 items-center justify-between gap-3">
              <p className="truncate text-xs text-muted-foreground">
                {useSiteKey ? "On — send site key with requests" : "Off — browse without a site key"}
              </p>
              <Switch
                checked={useSiteKey}
                onCheckedChange={setUseSiteKey}
                aria-label="Send site key with Muse requests"
              />
            </div>
          </div>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {messages.map((m) => (
            <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={
                  m.role === "user"
                    ? "max-w-[80%] bg-ink px-3 py-2 text-sm text-ink-foreground"
                    : m.denied
                      ? "max-w-[80%] border border-ink bg-background px-3 py-2 text-sm text-ink"
                      : "max-w-[80%] border border-ink/15 bg-frost px-3 py-2 text-sm text-ink"
                }
              >
                {m.role === "muse" && (
                  <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                    Muse{m.modelLabel ? ` · ${m.modelLabel}` : ""}
                  </p>
                )}
                <p className="whitespace-pre-wrap">{m.text}</p>
              </div>
            </div>
          ))}
          {busy && <p className="font-mono text-xs uppercase tracking-wider text-muted-foreground">Muse is browsing…</p>}
          <div ref={endRef} />
        </div>
        <form
          className="flex gap-2 border-t border-ink/10 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Paste a link and ask a question"
            disabled={busy}
          />
          <Button type="submit" disabled={busy || !draft.trim()}>
            Send
          </Button>
        </form>
      </Panel>
    </>
  );
}
