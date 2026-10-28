import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Panel } from "@/components/aurif/ui";
import { chatWithMuse, refreshActivity, useActiveSite } from "@/lib/aurif-store";
import { aurifHead } from "@/lib/aurif-meta";

export const Route = createFileRoute("/dashboard/agent")({
  head: () => aurifHead("Agent dashboard", "Ask Muse to try an Aurif site with a site key."),
  component: AgentDashboard,
});

type ChatMessage = { id: string; role: "user" | "muse"; text: string; denied?: boolean };

function AgentDashboard() {
  const site = useActiveSite();
  const [siteKey, setSiteKey] = useState(site.siteKey);
  const [draft, setDraft] = useState("Try the shop page and tell me what you can see.");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "intro",
      role: "muse",
      text: "I am Muse. Paste the site key, then tell me which page to open. If the key is missing or wrong, I will say access denied.",
    },
  ]);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setSiteKey(site.siteKey);
  }, [site.id, site.siteKey]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const send = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text }]);
    setBusy(true);
    try {
      const res = await chatWithMuse({ message: text, site_key: siteKey.trim() });
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "muse", text: res.reply, denied: res.denied },
      ]);
      await refreshActivity(site.id);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "muse",
          denied: true,
          text: err instanceof Error ? err.message : "Muse could not reach Aurif.",
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
        description="Chat with Muse. It calls Aurif with the site key you paste and reports what the site returned."
      />
      <Panel className="flex h-[calc(100vh-14rem)] min-h-[28rem] flex-col">
        <div className="border-b border-ink/10 px-4 py-3">
          <label className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground" htmlFor="site-key">
            Site key
          </label>
          <Input
            id="site-key"
            className="mt-1.5 font-mono text-xs"
            value={siteKey}
            onChange={(e) => setSiteKey(e.target.value)}
            placeholder="Paste the site key"
            autoComplete="off"
          />
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
                  <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Muse</p>
                )}
                <p className="whitespace-pre-wrap">{m.text}</p>
              </div>
            </div>
          ))}
          {busy && <p className="font-mono text-xs uppercase tracking-wider text-muted-foreground">Muse is requesting…</p>}
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
            placeholder="Ask Muse to open a page, or clear the key and try again"
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
