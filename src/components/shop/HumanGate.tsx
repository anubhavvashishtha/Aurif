import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  checkHuman,
  clearHumanToken,
  fetchChallenge,
  fetchGate,
  verifyHumanDrawing,
  type Challenge,
} from "@/lib/human-gate";

const API_BASE = import.meta.env.VITE_AURIF_API ?? "http://127.0.0.1:8787";

export function HumanGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [siteName, setSiteName] = useState("Northline Goods");
  const [hasInk, setHasInk] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);

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
      await verifyHumanDrawing(challenge.challenge_id, image);
      setAllowed(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Verification failed");
      try {
        const ch = await fetchChallenge();
        setChallenge(ch);
      } catch {
        /* keep old challenge */
      }
    } finally {
      setBusy(false);
    }
  };

  if (!ready) {
    return <AurifShell><p className="font-mono text-xs uppercase tracking-[0.22em] text-white/70">Aurif is checking human access…</p></AurifShell>;
  }

  if (allowed) return <>{children}</>;

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
        <h1 className="mt-2 font-mono text-3xl leading-tight tracking-tight text-white" style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
          This check is Aurif.
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-white/75">
          The shop stays closed until a person draws the code. Aurif sends the sketch to a vision model.
          Agents do not solve this screen — they use the Aurif protocol.
        </p>

        {challenge?.prompt && (
          <div className="mt-5 space-y-3">
            <div className="border border-white/15 bg-white px-4 py-3 text-center text-black">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-black/50">Draw this</p>
              <p className="mt-1 font-mono text-4xl font-medium tracking-[0.22em]">{challenge.target}</p>
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

        <div className="mt-5 grid gap-3 border border-white/15 p-3 sm:grid-cols-2">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/45">Humans</p>
            <p className="mt-1 text-xs leading-relaxed text-white/80">Draw on this Aurif pad. The shop opens only after the vision check.</p>
          </div>
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/45">Agents</p>
            <ol className="mt-1 list-decimal space-y-0.5 pl-4 font-mono text-[10px] leading-relaxed text-white/80">
              <li>GET /.well-known/aurif.json</li>
              <li>POST /ai/handshake</li>
              <li>GET /ai/page · POST /ai/actions</li>
            </ol>
            <p className="mt-1 font-mono text-[10px] text-white/40">{API_BASE}</p>
          </div>
        </div>
      </div>
    </AurifShell>
  );
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
