import { useEffect, useState, type ReactNode } from "react";
import { checkHuman, fetchGate, setHumanToken } from "@/lib/human-gate";

const AURIF_UI = import.meta.env.VITE_AURIF_UI ?? "http://127.0.0.1:5174";
const AURIF_HUMAN_MESSAGE = "aurif:human";

/** Embeds the Aurif human gate. Drawing, vision, and challenge code live in Aurif UI. */
export function HumanGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const gate = await fetchGate();
        if (cancelled) return;
        if (!gate.require_human_captcha) {
          setAllowed(true);
          setReady(true);
          return;
        }
        const ok = await checkHuman();
        if (cancelled) return;
        setAllowed(ok);
        setReady(true);
      } catch {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const origin = new URL(AURIF_UI).origin;
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== origin) return;
      const data = event.data as { type?: string; token?: string } | null;
      if (!data || data.type !== AURIF_HUMAN_MESSAGE || typeof data.token !== "string" || !data.token) return;
      setHumanToken(data.token);
      setAllowed(true);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#111] font-mono text-xs uppercase tracking-[0.22em] text-white/70">
        Aurif is checking human access…
      </div>
    );
  }

  if (allowed) return <>{children}</>;

  return (
    <iframe
      title="Aurif human gate"
      src={`${AURIF_UI}/gate?embed=1`}
      className="fixed inset-0 h-screen w-screen border-0 bg-[#111]"
    />
  );
}
