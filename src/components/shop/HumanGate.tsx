import { useEffect, useState, type ReactNode } from "react";
import { checkHuman, fetchChallenge, fetchGate, verifyHuman, type Challenge } from "@/lib/human-gate";

const API_BASE = import.meta.env.VITE_AURIF_API ?? "http://127.0.0.1:8787";

export function HumanGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [siteName, setSiteName] = useState("Northline Goods");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const gate = await fetchGate();
        if (cancelled) return;
        setSiteName(gate.site_name || "Northline Goods");
        if (!gate.require_human_captcha) {
          setAllowed(true);
          setReady(true);
          return;
        }
        const ok = await checkHuman();
        if (cancelled) return;
        if (ok) {
          setAllowed(true);
          setReady(true);
          return;
        }
        const ch = await fetchChallenge();
        if (cancelled) return;
        setChallenge(ch);
        setReady(true);
      } catch {
        if (!cancelled) {
          setError("Could not reach Aurif gate API. Is the server running on :8787?");
          setReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center bg-background text-sm text-muted-foreground">
        Checking human access…
      </div>
    );
  }

  if (allowed) return <>{children}</>;

  return (
    <div className="grid min-h-screen place-items-center bg-background px-4">
      <div className="w-full max-w-md animate-in fade-in space-y-5 rounded-xl border bg-card p-6 shadow-sm">
        <div>
          <p className="font-serif text-3xl text-foreground">{siteName}</p>
          <h1 className="mt-2 text-xl font-semibold tracking-tight">Human verification</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Only humans can use this storefront. AI agents must identify through Aurif and use the
            machine endpoints.
          </p>
        </div>

        {challenge?.prompt && (
          <form
            className="space-y-3"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                await verifyHuman(challenge.challenge_id || "", answer);
                setAllowed(true);
              } catch (err: any) {
                setError(err.message || "Wrong answer");
                const ch = await fetchChallenge();
                setChallenge(ch);
                setAnswer("");
              } finally {
                setBusy(false);
              }
            }}
          >
            <label className="block text-sm font-medium">{challenge.prompt}</label>
            <input
              className="flex h-10 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              inputMode="numeric"
              autoFocus
              required
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            <button
              type="submit"
              disabled={busy}
              className="inline-flex h-10 w-full items-center justify-center rounded-md bg-primary text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {busy ? "Checking…" : "Continue to shop"}
            </button>
          </form>
        )}

        <div className="rounded-lg border border-dashed bg-muted/40 p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">For AI agents</p>
          <ol className="mt-2 list-decimal space-y-1 pl-4 font-mono">
            <li>GET {API_BASE}/.well-known/aurif.json</li>
            <li>POST {API_BASE}/ai/handshake</li>
            <li>GET {API_BASE}/ai/page · POST {API_BASE}/ai/actions</li>
          </ol>
        </div>
      </div>
    </div>
  );
}
