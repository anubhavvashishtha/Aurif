import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  AURIF_HUMAN_MESSAGE,
  checkHuman,
  clearHumanToken,
  fetchChallenge,
  fetchGate,
  HumanVerifyError,
  verifyHumanDrawing,
  type AgentAccessHint,
  type Challenge,
} from "@/lib/human-gate";

const API_BASE = import.meta.env.VITE_AURIF_API ?? "http://127.0.0.1:8787";

const DEFAULT_AGENT_HINT: AgentAccessHint = {
  title: "Use the API with a site key",
  message:
    "In order to access this page as an agent, send a GET or POST request to the Aurif API with the required site key. The human storefront will not open from a failed drawing.",
  steps: [
    { method: "GET", path: "/ai/help", note: "Open help — no site key" },
    { method: "POST", path: "/ai/handshake", note: "Include site_key in the body or X-Aurif-Site-Key header" },
    { method: "GET", path: "/ai/page?path=/", note: "Send X-Aurif-Site-Key and the session from handshake" },
  ],
  api_base: API_BASE,
  site_key_header: "X-Aurif-Site-Key",
};

export function HumanGate({ embed = false }: { embed?: boolean }) {
  const [ready, setReady] = useState(false);
  const [passed, setPassed] = useState(false);
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [siteName, setSiteName] = useState("this site");
  const [hasInk, setHasInk] = useState(false);
  const [required, setRequired] = useState(true);
  const [agentModal, setAgentModal] = useState<AgentAccessHint | null>(null);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);

  const release = (token: string) => {
    setPassed(true);
    if (embed && token && typeof window !== "undefined" && window.parent !== window) {
      window.parent.postMessage({ type: AURIF_HUMAN_MESSAGE, token }, "*");
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const gate = await fetchGate();
        if (cancelled) return;
        setSiteName(gate.site_name || "this site");
        if (!gate.require_human_captcha) {
          setRequired(false);
          setReady(true);
          if (embed) {
            const issued = await fetch(`${API_BASE}/api/public/human-verify`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              credentials: "include",
              body: "{}",
            });
            if (cancelled) return;
            const data = (await issued.json()) as { human_token?: string };
            if (data.human_token) release(data.human_token);
          }
          return;
        }
        const ok = await checkHuman();
        if (cancelled) return;
        if (ok) {
          release(getStoredToken());
          setReady(true);
          return;
        }
        const ch = await fetchChallenge();
        if (cancelled) return;
        setChallenge(ch);
        setReady(true);
      } catch {
        if (!cancelled) {
          setError(`Could not reach the Aurif API at ${API_BASE}. Is the server running?`);
          setReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [embed]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !challenge) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const cssW = canvas.clientWidth || 360;
    const cssH = 200;
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#fafaf8";
    ctx.fillRect(0, 0, cssW, cssH);
    ctx.strokeStyle = "#e5e2da";
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, cssW - 1, cssH - 1);
    setHasInk(false);
  }, [challenge?.challenge_id]);

  const pos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    drawing.current = true;
    canvas.setPointerCapture(e.pointerId);
    const { x, y } = pos(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#1a1a18";
    ctx.lineWidth = 3.5;
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const { x, y } = pos(e);
    ctx.lineTo(x, y);
    ctx.stroke();
    setHasInk(true);
  };

  const onPointerUp = () => {
    drawing.current = false;
  };

  const clearPad = () => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const cssW = canvas.clientWidth || 360;
    const cssH = 200;
    ctx.fillStyle = "#fafaf8";
    ctx.fillRect(0, 0, cssW, cssH);
    ctx.strokeStyle = "#e5e2da";
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, cssW - 1, cssH - 1);
    setHasInk(false);
    setError(null);
  };

  const submit = async () => {
    if (!challenge?.challenge_id || !canvasRef.current) return;
    if (!hasInk) {
      setError("Draw the characters on the pad first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const image = canvasRef.current.toDataURL("image/png");
      const data = await verifyHumanDrawing(challenge.challenge_id, image);
      release(data.human_token);
    } catch (err: unknown) {
      const verifyErr = err instanceof HumanVerifyError ? err : null;
      setError(verifyErr?.message || (err instanceof Error ? err.message : "Verification failed"));
      // Failed drawing → do not open the site. Show agent API / site-key instructions.
      setAgentModal(verifyErr?.agentAccess || DEFAULT_AGENT_HINT);
      try {
        const ch = await fetchChallenge();
        setChallenge(ch);
      } catch {
        /* keep the current challenge */
      }
    } finally {
      setBusy(false);
    }
  };

  if (!ready) {
    return (
      <AurifShell>
        <p className="font-mono text-xs uppercase tracking-[0.22em] text-white/70">Aurif human gate</p>
      </AurifShell>
    );
  }

  if (!required || passed) {
    return (
      <AurifShell>
        <div className="w-full max-w-lg border border-white/15 bg-black/75 p-6 text-white">
          <p className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-[0.2em]">
            <span className="grid size-7 place-items-center bg-white text-[11px] text-black">A</span>
            Aurif
          </p>
          <h1 className="mt-6 font-mono text-3xl text-white">Human check passed.</h1>
          <p className="mt-3 text-sm text-white/75">
            {embed ? `Opening ${siteName}.` : `${siteName} can let this browser through. Agents still use the Aurif protocol.`}
          </p>
        </div>
      </AurifShell>
    );
  }

  return (
    <AurifShell>
      <div className="w-full max-w-lg border border-white/15 bg-black/75 p-6 text-white shadow-[0_0_0_1px_rgba(255,255,255,0.04)] backdrop-blur-md">
        <div className="flex items-center justify-between gap-3">
          <p className="inline-flex items-center gap-2 font-mono text-xs font-medium uppercase tracking-[0.2em]">
            <span className="grid size-7 place-items-center bg-white font-mono text-[11px] text-black">A</span>
            Aurif
          </p>
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/55">Human gate</p>
        </div>

        <p className="mt-6 font-mono text-[11px] uppercase tracking-[0.18em] text-white/50">Protecting {siteName}</p>
        <h1 className="mt-2 font-mono text-3xl leading-tight tracking-tight text-white">This check is Aurif.</h1>
        <p className="mt-3 text-sm leading-relaxed text-white/75">
          The shop stays closed until a person draws the code. Aurif sends the sketch to a vision model.
          Agents do not solve this screen — they use the Aurif protocol.
        </p>

        {challenge?.prompt && (
          <div className="mt-5 space-y-3">
            <div className="border border-white/15 bg-white px-4 py-3 text-center text-black">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-black/50">Draw this</p>
              {challenge.image ? (
                <img
                  src={challenge.image}
                  alt="Characters to draw"
                  className="mx-auto mt-2 h-16 max-w-full object-contain"
                />
              ) : null}
              <p className="mt-2 text-sm text-black/70">{challenge.prompt}</p>
            </div>

            <canvas
              ref={canvasRef}
              className="h-[200px] w-full touch-none cursor-crosshair border border-white/20 bg-[#fafaf8]"
              style={{ touchAction: "none" }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerLeave={onPointerUp}
            />

            {challenge.hint && <p className="text-xs text-white/55">{challenge.hint}</p>}
            {error && <p className="text-sm text-red-300">{error}</p>}

            <div className="flex gap-2">
              <button
                type="button"
                onClick={clearPad}
                disabled={busy}
                className="inline-flex h-10 flex-1 items-center justify-center border border-white/25 font-mono text-xs uppercase tracking-wider text-white disabled:opacity-40"
              >
                Clear
              </button>
              <button
                type="button"
                onClick={() => void submit()}
                disabled={busy || !hasInk}
                className="inline-flex h-10 flex-[2] items-center justify-center bg-white font-mono text-xs uppercase tracking-wider text-black disabled:opacity-40"
              >
                {busy ? "Aurif is reading…" : "Verify with Aurif"}
              </button>
            </div>
            <button
              type="button"
              className="font-mono text-[11px] uppercase tracking-wider text-white/50 underline"
              onClick={() => {
                clearHumanToken();
                void fetchChallenge().then(setChallenge);
                clearPad();
              }}
            >
              New challenge
            </button>
          </div>
        )}

        {!challenge?.prompt && error && <p className="mt-4 text-sm text-red-300">{error}</p>}
      </div>

      {agentModal && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/70 px-4"
          role="dialog"
          aria-modal="true"
          data-testid="aurif-agent-access-modal"
        >
          <div className="w-full max-w-md border border-white/20 bg-[#111] p-5 text-white shadow-2xl">
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/50">Access denied</p>
            <h2 className="mt-2 font-mono text-2xl text-white">{agentModal.title || DEFAULT_AGENT_HINT.title}</h2>
            <p className="mt-3 text-sm leading-relaxed text-white/75">
              {agentModal.message || DEFAULT_AGENT_HINT.message}
            </p>
            <ol className="mt-4 space-y-2 border border-white/15 bg-black/40 p-3 font-mono text-[11px] text-white/85">
              {(agentModal.steps || DEFAULT_AGENT_HINT.steps || []).map((step) => (
                <li key={`${step.method}-${step.path}`}>
                  <span className="text-white">{step.method}</span>{" "}
                  <span className="text-white/90">{(agentModal.api_base || API_BASE) + step.path}</span>
                  {step.note ? <span className="mt-0.5 block text-white/50">{step.note}</span> : null}
                </li>
              ))}
            </ol>
            <p className="mt-3 font-mono text-[10px] text-white/45">
              Required credential header: {agentModal.site_key_header || "X-Aurif-Site-Key"}
            </p>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                className="inline-flex h-10 flex-1 items-center justify-center border border-white/25 font-mono text-xs uppercase tracking-wider"
                onClick={() => {
                  setAgentModal(null);
                  clearPad();
                }}
              >
                Try drawing again
              </button>
              <button
                type="button"
                className="inline-flex h-10 flex-1 items-center justify-center bg-white font-mono text-xs uppercase tracking-wider text-black"
                onClick={() => setAgentModal(null)}
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </AurifShell>
  );
}

function getStoredToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("aurif_human_token") || "";
}

function AurifShell({ children }: { children: ReactNode }) {
  return (
    <div
      className="grid min-h-screen place-items-center bg-[#111] px-4 py-10 text-white"
      style={{
        backgroundImage:
          "linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.08) 1px, transparent 1px)",
        backgroundSize: "48px 48px",
      }}
    >
      {children}
    </div>
  );
}
