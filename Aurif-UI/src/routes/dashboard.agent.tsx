import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
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
  type MuseStep,
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
  steps?: string[];
  pending?: boolean;
};

function stepCaption(step: MuseStep): string | null {
  const action = String(step.action || "");
  const result = String(step.result || "");
  const actionId = step.action_id ? String(step.action_id) : "";
  const url = String(step.url || "");
  if (action === "open_url" && result === "started") return "Tried the page";
  if (action === "open_url" && result === "failed") return "Could not reach the page";
  if (action === "open_url" && result === "blocked") return "Page blocked automated access";
  if (action === "open_url" && result === "ok") return "Page loaded";
  if (action === "check_captcha_required" || (action === "fetch_captcha" && result === "skipped")) {
    return "Human verification is off";
  }
  if (action === "fetch_captcha" && result === "failed") return "Could not run human verification";
  if (action === "fetch_captcha") return "Human verification requested";
  if (action === "solve_captcha") return "Blocked by human verification";
  if (action === "switch_to_api") return "Used the site key";
  if (action === "stop") return "Stopped";
  if (action === "follow_up") return "Read the page";
  if (action === "request" && url.includes("/ai/help")) return null;
  if (action === "request" && result === "failed") {
    return actionId ? `API refused ${actionId}` : "API refused the request";
  }
  if (action === "request" && result === "ok") {
    if (actionId.startsWith("product.add:")) return "Called the API to add the item";
    if (actionId === "cart.checkout") return "Called the API to check out";
    if (actionId === "cart.clear") return "Called the API to clear the cart";
    if (actionId) return `Called the API (${actionId})`;
    if (url.includes("/ai/handshake")) return "Called the Aurif API";
    if (url.includes("/ai/page")) return "Read the page from the API";
    return "Called the Aurif API";
  }
  return null;
}

function captionsFor(steps: MuseStep[] | undefined): string[] {
  const out: string[] = [];
  for (const step of steps || []) {
    const caption = stepCaption(step);
    if (caption && caption !== out[out.length - 1]) out.push(caption);
  }
  return out;
}

function pushCaption(steps: string[] | undefined, caption: string | null): string[] | undefined {
  if (!caption || caption === steps?.[steps.length - 1]) return steps;
  return [...(steps || []), caption];
}

function AgentDashboard() {
  const site = useActiveSite();
  const [useSiteKey, setUseSiteKey] = useState(false);
  const [models, setModels] = useState<AgentModel[]>([]);
  const [modelId, setModelId] = useState("");
  const [modelWarning, setModelWarning] = useState<string | null>(null);
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
        if (health?.degraded) {
          const detail = [health.text?.last_error, health.vision?.last_error].filter(Boolean).join("; ");
          setModelWarning(
            detail
              ? `Model degraded (${detail}). Handshake uses keyword rules. The human gate can fall back without vision. Act is not granted automatically.`
              : "Model key missing or the last call failed. Handshake uses keyword rules. The human gate can fall back without vision. Act is not granted automatically.",
          );
        } else {
          setModelWarning(null);
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
    const liveId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", text },
      { id: liveId, role: "muse", text: "", pending: true, steps: [] },
    ]);
    setBusy(true);
    try {
      const res = await chatWithMuse(
        {
          message: text,
          use_site_key: useSiteKey,
          site_key: useSiteKey ? site.siteKey : undefined,
          model: modelId || undefined,
        },
        (step) => {
          const caption = stepCaption(step);
          setMessages((prev) =>
            prev.map((m) => (m.id === liveId ? { ...m, steps: pushCaption(m.steps, caption) } : m)),
          );
        },
      );
      const used =
        res.model?.label ||
        selected?.label ||
        res.model?.id ||
        modelId ||
        undefined;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === liveId
            ? {
                ...m,
                text: res.reply,
                denied: res.denied,
                modelLabel: used,
                pending: false,
                steps: captionsFor(res.steps),
              }
            : m,
        ),
      );
      await refreshActivity(site.id);
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === liveId
            ? {
                ...m,
                pending: false,
                denied: true,
                text: err instanceof Error ? err.message : "Muse could not reach the site.",
              }
            : m,
        ),
      );
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
      {modelWarning && (
        <p className="mb-3 border border-ink/20 bg-frost px-3 py-2 text-sm text-ink" role="status">
          {modelWarning}
        </p>
      )}
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
              {selected ? `Using ${selected.label} via ${selected.provider}` : "Server default model"}
            </p>
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
                {m.pending && (
                  <p className="mb-2 flex items-center gap-2 text-sm text-ink">
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                    Working through the steps
                  </p>
                )}
                {m.text && <p className="whitespace-pre-wrap">{m.text}</p>}
                {m.steps && m.steps.length > 0 && (
                  <ol
                    className={
                      m.text
                        ? "mt-2 space-y-1 border-t border-ink/10 pt-2 text-sm text-ink"
                        : "space-y-1 text-sm text-ink"
                    }
                    aria-live={m.pending ? "polite" : undefined}
                  >
                    {m.steps.map((step, index) => (
                      <li key={`${m.id}-${index}`}>
                        {index + 1}. {step}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
          ))}
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
