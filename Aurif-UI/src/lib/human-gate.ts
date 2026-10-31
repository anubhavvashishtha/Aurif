const API_BASE = import.meta.env.VITE_AURIF_API ?? "http://127.0.0.1:8787";
const TOKEN_KEY = "aurif_human_token";

export const AURIF_HUMAN_MESSAGE = "aurif:human";

export type Challenge = {
  required: boolean;
  challenge_id?: string;
  type?: string;
  kind?: string;
  target?: string;
  prompt?: string;
  hint?: string;
};

export type GateStatus = {
  ok?: boolean;
  site_name?: string;
  require_human_captcha?: boolean;
  api_base?: string;
};

export function getHumanToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setHumanToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  document.cookie = `aurif_human=${encodeURIComponent(token)}; path=/; max-age=${60 * 60 * 12}; SameSite=Lax`;
}

export function clearHumanToken() {
  localStorage.removeItem(TOKEN_KEY);
  document.cookie = "aurif_human=; path=/; max-age=0";
}

export async function fetchGate(): Promise<GateStatus> {
  const res = await fetch(`${API_BASE}/api/public/gate`);
  return res.json();
}

export async function fetchChallenge(): Promise<Challenge> {
  const res = await fetch(`${API_BASE}/api/public/human-challenge`);
  return res.json();
}

export type AgentAccessHint = {
  title?: string;
  message?: string;
  steps?: { method: string; path: string; note?: string }[];
  api_base?: string;
  site_key_header?: string;
};

export class HumanVerifyError extends Error {
  agentAccess?: AgentAccessHint;
  verdict?: { read_as?: string; human_like?: boolean; match?: boolean; model?: string };

  constructor(message: string, extra?: { agentAccess?: AgentAccessHint; verdict?: HumanVerifyError["verdict"] }) {
    super(message);
    this.name = "HumanVerifyError";
    this.agentAccess = extra?.agentAccess;
    this.verdict = extra?.verdict;
  }
}

export async function verifyHumanDrawing(challengeId: string, imageDataUrl: string) {
  const res = await fetch(`${API_BASE}/api/public/human-verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ challenge_id: challengeId, image: imageDataUrl }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    const detail = data.verdict?.read_as ? ` (read as “${data.verdict.read_as}”)` : "";
    throw new HumanVerifyError((data.error || "Verification failed") + detail, {
      agentAccess: data.agent_access,
      verdict: data.verdict,
    });
  }
  if (data.human_token) setHumanToken(data.human_token);
  return data as { ok: boolean; human_token: string; verdict?: { read_as?: string; model?: string } };
}

export async function checkHuman(): Promise<boolean> {
  const token = getHumanToken();
  const res = await fetch(`${API_BASE}/api/public/human-check`, {
    headers: token ? { "X-Aurif-Human": token } : {},
    credentials: "include",
  });
  const data = await res.json();
  if (!data.required) return true;
  return !!data.ok;
}
