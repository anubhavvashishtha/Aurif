import { useSyncExternalStore } from "react";
import { API_BASE, api, clearToken, getToken, setToken } from "./api";
import type { JsonValue, RequestField, ResponseField } from "./aurif-fields";

/**
 * Aurif dashboard store — hydrated from Flask `/api/*`.
 * Keeps the same sync React API the Lovable UI expects.
 */

export type EventKind =
  | "handshake"
  | "page"
  | "action"
  | "page_blocked"
  | "action_blocked"
  | "handshake_denied"
  | "field_redacted";

export interface MetaModelRef {
  id?: string;
  provider?: string;
  label?: string;
}

export interface PurposeRisk {
  risk: string;
  reason: string;
  source?: string;
  degraded?: boolean;
  fallback?: string | null;
  warning?: string;
  latencyMs?: number;
  dropAct?: boolean;
  model?: MetaModelRef;
}

export interface AgentEvent {
  id: string;
  time: string;
  agentId: string;
  kind: EventKind;
  target: string;
  redactedFields?: string[];
  accepted?: boolean;
  reason?: string;
  asked?: unknown;
  navigated?: string[];
  purpose?: string;
  grantedScopes?: string[];
  purposeRisk?: PurposeRisk;
}

export interface Endpoint {
  id: string;
  label: string;
  kind: "page" | "action" | "api";
  ref: string;
  agentAccess: boolean;
  direction: "read" | "write" | "both";
  responseFields: ResponseField[];
  requestFields: RequestField[];
  sampleResponse: JsonValue;
  sampleRequest: JsonValue;
}

export interface Site {
  id: string;
  name: string;
  url: string;
  siteKey: string;
  welcome: string;
  blockedAgents: string;
  blockAnonymousAgents: boolean;
  requireHumanCaptcha: boolean;
  endpoints: Endpoint[];
  events: AgentEvent[];
}

interface State {
  user: { email: string } | null;
  activeSiteId: string;
  sites: Site[];
  ready: boolean;
}

const listeners = new Set<() => void>();
let state: State = { user: null, activeSiteId: "", sites: [], ready: false };
let bootPromise: Promise<void> | null = null;

function emit() {
  listeners.forEach((l) => l());
}

function mapEndpoint(raw: any): Endpoint {
  return {
    id: raw.id,
    label: raw.label,
    kind: raw.kind === "action" ? "action" : raw.kind === "api" ? "api" : "page",
    ref: raw.ref || raw.path || raw.action_id || raw.id,
    agentAccess: !!raw.agent_access,
    direction: raw.direction || (raw.kind === "action" ? "both" : "read"),
    responseFields: (raw.response_fields || []).map((f: any) => ({
      key: f.key,
      label: f.label || f.key,
      type: f.type || "string",
      agentVisible: f.agent_visible !== false,
    })),
    requestFields: (raw.request_fields || []).map((f: any) => ({
      key: f.key,
      label: f.label || f.key,
      agentAllowed: f.agent_allowed !== false,
    })),
    sampleResponse: (raw.sample_response || {}) as JsonValue,
    sampleRequest: (raw.sample_request || {}) as JsonValue,
  };
}

function mapModelRef(model: unknown): MetaModelRef | undefined {
  if (!model) return undefined;
  if (typeof model === "string") return { id: model, label: model };
  if (typeof model === "object") {
    const row = model as MetaModelRef;
    return { id: row.id, provider: row.provider, label: row.label || row.id };
  }
  return undefined;
}

function mapPurposeRisk(raw: unknown): PurposeRisk | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const risk = raw as Record<string, unknown>;
  const level = String(risk.risk || "").toLowerCase();
  if (!level) return undefined;
  return {
    risk: level,
    reason: String(risk.reason || ""),
    source: typeof risk.source === "string" ? risk.source : undefined,
    degraded: Boolean(risk.degraded),
    fallback: typeof risk.fallback === "string" ? risk.fallback : risk.source === "rules" ? "keyword_rules" : null,
    warning: typeof risk.warning === "string" ? risk.warning : undefined,
    latencyMs: typeof risk.latency_ms === "number" ? risk.latency_ms : undefined,
    dropAct: Boolean(risk.drop_act),
    model: mapModelRef(risk.model),
  };
}

function mapEvent(raw: any): AgentEvent {
  const kind = (raw.kind || "page") as EventKind;
  const detail = raw.detail || {};
  const asked = detail.asked;
  const askedLabel =
    asked && typeof asked === "object"
      ? [asked.method, asked.path || asked.action_id, asked.query?.path].filter(Boolean).join(" ")
      : "";
  const scopes = Array.isArray(detail.granted_scopes)
    ? detail.granted_scopes.filter((scope: unknown) => typeof scope === "string")
    : undefined;
  return {
    id: raw.id || crypto.randomUUID(),
    time: raw.ts ? new Date(raw.ts * 1000).toISOString() : new Date().toISOString(),
    agentId: raw.agent_id || "agent",
    kind,
    target: askedLabel || raw.path || raw.action_id || detail.reason || "—",
    redactedFields: detail.redacted_fields,
    accepted: typeof detail.accepted === "boolean" ? detail.accepted : undefined,
    reason: detail.reason,
    asked,
    navigated: Array.isArray(detail.navigated) ? detail.navigated.filter(Boolean) : raw.path ? [raw.path] : [],
    purpose: typeof detail.purpose === "string" ? detail.purpose : undefined,
    grantedScopes: scopes,
    purposeRisk: mapPurposeRisk(detail.purpose_risk),
  };
}

function mapSite(raw: any): Site {
  return {
    id: raw.id,
    name: raw.name,
    url: raw.url || "",
    siteKey: raw.site_key,
    welcome: raw.agent_welcome || "",
    blockedAgents: (raw.blocked_agents || []).join(", "),
    blockAnonymousAgents: raw.block_anonymous_agents !== false,
    requireHumanCaptcha: raw.require_human_captcha !== false,
    endpoints: (raw.endpoints || []).map(mapEndpoint),
    events: (raw.activity || []).map(mapEvent),
  };
}

function replaceSite(site: Site) {
  state = {
    ...state,
    sites: state.sites.some((s) => s.id === site.id)
      ? state.sites.map((s) => (s.id === site.id ? site : s))
      : [...state.sites, site],
    activeSiteId: state.activeSiteId || site.id,
  };
  emit();
}

async function hydrateFromMe() {
  const data = await api<{ user: { email: string }; sites: any[] }>("/api/auth/me");
  const sites = (data.sites || []).map(mapSite);
  state = {
    user: { email: data.user.email },
    sites,
    activeSiteId: sites[0]?.id || "",
    ready: true,
  };
  emit();
}

export async function bootstrap() {
  if (bootPromise) return bootPromise;
  bootPromise = (async () => {
    if (!getToken()) {
      state = { ...state, ready: true };
      emit();
      return;
    }
    try {
      await hydrateFromMe();
    } catch {
      clearToken();
      state = { user: null, activeSiteId: "", sites: [], ready: true };
      emit();
    }
  })();
  return bootPromise;
}

void bootstrap();

export function useAurif<T>(select: (s: State) => T): T {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => select(state),
    () => select(state),
  );
}

export const getState = () => state;

export async function login(email: string, password: string): Promise<string | null> {
  if (!email.includes("@") || password.length < 6) {
    return "Enter a valid email and a password of 6+ characters.";
  }
  try {
    const data = await api<{ token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(data.token);
    await hydrateFromMe();
    return null;
  } catch (e: any) {
    return e.message || "Login failed";
  }
}

export async function signup(email: string, password: string): Promise<string | null> {
  if (!email.includes("@") || password.length < 6) {
    return "Enter a valid email and a password of 6+ characters.";
  }
  try {
    const data = await api<{ token: string }>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, name: email.split("@")[0] }),
    });
    setToken(data.token);
    // ensure at least one site
    try {
      await api("/api/sites", {
        method: "POST",
        body: JSON.stringify({
          name: "My website",
          url: import.meta.env.VITE_CUSTOMER_SITE_URL ?? "http://127.0.0.1:5173",
        }),
      });
    } catch {
      /* demo-shop may already exist for seeded owner only */
    }
    await hydrateFromMe();
    return null;
  } catch (e: any) {
    return e.message || "Signup failed";
  }
}

export async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {
    /* ignore */
  }
  clearToken();
  state = { user: null, activeSiteId: "", sites: [], ready: true };
  emit();
}

export const setActiveSite = (id: string) => {
  state = { ...state, activeSiteId: id };
  emit();
};

export async function updateSite(
  id: string,
  data: Partial<
    Pick<Site, "name" | "url" | "welcome" | "blockedAgents" | "blockAnonymousAgents" | "requireHumanCaptcha">
  >,
) {
  const body: Record<string, unknown> = {};
  if (data.name !== undefined) body.name = data.name;
  if (data.url !== undefined) body.url = data.url;
  if (data.welcome !== undefined) body.agent_welcome = data.welcome;
  if (data.blockAnonymousAgents !== undefined) {
    body.block_anonymous_agents = data.blockAnonymousAgents;
  }
  if (data.requireHumanCaptcha !== undefined) {
    body.require_human_captcha = data.requireHumanCaptcha;
  }
  if (data.blockedAgents !== undefined) {
    body.blocked_agents = data.blockedAgents
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }
  const res = await api<{ site: any }>(`/api/sites/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  const current = state.sites.find((s) => s.id === id);
  replaceSite({ ...mapSite(res.site), events: current?.events || [] });
}

export async function rotateKey(id: string) {
  const res = await api<{ site: any }>(`/api/sites/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ rotate_site_key: true }),
  });
  const current = state.sites.find((s) => s.id === id);
  replaceSite({ ...mapSite(res.site), events: current?.events || [] });
}

export async function toggleEndpoint(siteId: string, endpointId: string, on: boolean) {
  // optimistic
  const site = state.sites.find((s) => s.id === siteId);
  if (site) {
    replaceSite({
      ...site,
      endpoints: site.endpoints.map((e) => (e.id === endpointId ? { ...e, agentAccess: on } : e)),
    });
  }
  const res = await api<{ site: any }>(`/api/sites/${siteId}/endpoints/${encodeURIComponent(endpointId)}`, {
    method: "PUT",
    body: JSON.stringify({ agent_access: on }),
  });
  const current = state.sites.find((s) => s.id === siteId);
  replaceSite({ ...mapSite(res.site), events: current?.events || [] });
}

export async function updateResponseFields(
  siteId: string,
  endpointId: string,
  update: (fields: ResponseField[]) => ResponseField[],
) {
  const site = state.sites.find((s) => s.id === siteId);
  if (!site) return;
  const ep = site.endpoints.find((e) => e.id === endpointId);
  if (!ep) return;
  const next = update(ep.responseFields);
  replaceSite({
    ...site,
    endpoints: site.endpoints.map((e) => (e.id === endpointId ? { ...e, responseFields: next } : e)),
  });
  const res = await api<{ site: any }>(`/api/sites/${siteId}/endpoints/${encodeURIComponent(endpointId)}`, {
    method: "PUT",
    body: JSON.stringify({
      response_fields: next.map((f) => ({ key: f.key, agent_visible: f.agentVisible })),
    }),
  });
  const current = state.sites.find((s) => s.id === siteId);
  replaceSite({ ...mapSite(res.site), events: current?.events || [] });
}

export async function updateRequestField(
  siteId: string,
  endpointId: string,
  key: string,
  agentAllowed: boolean,
) {
  const site = state.sites.find((s) => s.id === siteId);
  if (!site) return;
  const ep = site.endpoints.find((e) => e.id === endpointId);
  if (!ep) return;
  const next = ep.requestFields.map((f) => (f.key === key ? { ...f, agentAllowed } : f));
  replaceSite({
    ...site,
    endpoints: site.endpoints.map((e) => (e.id === endpointId ? { ...e, requestFields: next } : e)),
  });
  const res = await api<{ site: any }>(`/api/sites/${siteId}/endpoints/${encodeURIComponent(endpointId)}`, {
    method: "PUT",
    body: JSON.stringify({
      request_fields: next.map((f) => ({ key: f.key, agent_allowed: f.agentAllowed })),
    }),
  });
  const current = state.sites.find((s) => s.id === siteId);
  replaceSite({ ...mapSite(res.site), events: current?.events || [] });
}

export async function refreshActivity(siteId: string) {
  const data = await api<{ events: any[] }>(`/api/sites/${siteId}/activity`);
  const site = state.sites.find((s) => s.id === siteId);
  if (!site) return;
  replaceSite({ ...site, events: (data.events || []).map(mapEvent) });
}

export interface MetaFeatureResponse {
  model: string;
  model_info?: MetaModelRef;
  latency_ms?: number | null;
  source?: string;
  degraded?: boolean;
  fallback?: string | null;
  warning?: string | null;
}

export async function proposePolicy(siteId: string, instruction: string) {
  return api<
    MetaFeatureResponse & {
      ok: boolean;
      proposal: {
        summary: string;
        patches: Array<Record<string, unknown>>;
        blocked_agents_add?: string[];
        source?: string;
        degraded?: boolean;
        fallback?: string | null;
        warning?: string | null;
        latency_ms?: number | null;
        model?: MetaModelRef | string;
      };
    }
  >(`/api/sites/${siteId}/ai/policy-propose`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
}

export async function applyPolicy(
  siteId: string,
  patches: Array<Record<string, unknown>>,
  blockedAgentsAdd: string[] = [],
) {
  const res = await api<{ site: any }>(`/api/sites/${siteId}/ai/policy-apply`, {
    method: "POST",
    body: JSON.stringify({ patches, blocked_agents_add: blockedAgentsAdd }),
  });
  const current = state.sites.find((s) => s.id === siteId);
  replaceSite({ ...mapSite(res.site), events: current?.events || [] });
}

export async function summarizeActivity(siteId: string) {
  return api<
    MetaFeatureResponse & {
      ok: boolean;
      summary: {
        summary: string;
        risks: string[];
        suggested_blocked_agents: string[];
        source?: string;
        degraded?: boolean;
        fallback?: string | null;
        warning?: string | null;
        latency_ms?: number | null;
        model?: MetaModelRef | string;
      };
    }
  >(`/api/sites/${siteId}/ai/activity-summary`, { method: "POST", body: "{}" });
}

export type MuseStep = {
  step?: number;
  action?: string;
  result?: string;
  detail?: string;
  url?: string;
  method?: string;
  status?: number;
  saw?: unknown;
  [key: string]: unknown;
};

export type AgentModel = {
  id: string;
  label: string;
  provider: string;
  default?: boolean;
};

export type ModelHealthSide = {
  degraded?: boolean;
  last_error?: string | null;
  key_configured?: boolean;
  provider?: string;
  model?: string;
};

export async function fetchAgentModels() {
  return api<{
    ok: boolean;
    models: AgentModel[];
    current?: AgentModel;
    health?: {
      degraded?: boolean;
      text?: ModelHealthSide;
      vision?: ModelHealthSide;
    };
  }>("/api/ai/models");
}

export type MuseChatResult = {
  ok: boolean;
  denied: boolean;
  reply: string;
  steps?: MuseStep[];
  path?: string;
  status?: number;
  fields?: { label: string; value: string }[];
  url?: string;
  model?: { id: string; provider: string; label: string };
};

export async function chatWithMuse(
  body: {
    message: string;
    site_key?: string;
    use_site_key?: boolean;
    model?: string;
  },
  onStep?: (step: MuseStep) => void,
) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["X-Aurif-Owner"] = token;
  const res = await fetch(API_BASE + "/api/ai/agent-chat", {
    method: "POST",
    headers,
    body: JSON.stringify({ ...body, stream: true }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { error?: string }).error || res.statusText || "Request failed");
  }
  if (!res.body) {
    const data = (await res.json()) as MuseChatResult;
    for (const step of data.steps || []) onStep?.(step);
    return data;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let final: MuseChatResult | null = null;
  const take = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const event = JSON.parse(trimmed) as { type?: string; step?: MuseStep; error?: string } & MuseChatResult;
    if (event.type === "step" && event.step) onStep?.(event.step);
    else if (event.type === "done") final = event;
    else if (event.type === "error") throw new Error(event.error || "Muse could not finish that.");
  };
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buf += decoder.decode(chunk.value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() || "";
    for (const line of lines) take(line);
  }
  if (buf.trim()) take(buf);
  if (!final) throw new Error("Muse did not finish that reply.");
  return final;
}

export const useActiveSite = () =>
  useAurif((s) => (s.sites.find((x) => x.id === s.activeSiteId) ?? s.sites[0]) as Site);

export const isBlockedKind = (k: EventKind) => k.endsWith("_blocked") || k === "handshake_denied";
