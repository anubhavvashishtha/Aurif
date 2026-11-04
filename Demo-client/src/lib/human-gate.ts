const API_BASE = import.meta.env.VITE_AURIF_API ?? "http://127.0.0.1:8787";
const TOKEN_KEY = "aurif_human_token";

/** Shop only stores the pass Aurif's gate sends back. The drawing check lives in Aurif UI. */
export function getHumanToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setHumanToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  document.cookie = `aurif_human=${encodeURIComponent(token)}; path=/; max-age=${60 * 60 * 12}; SameSite=Lax`;
}

export async function fetchGate() {
  const res = await fetch(`${API_BASE}/api/public/gate`);
  return res.json() as Promise<{ site_name?: string; require_human_captcha?: boolean }>;
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
