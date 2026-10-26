import { useSyncExternalStore } from "react";

/**
 * Aurif client-side mock store.
 * Every function below marks the API it should call once a backend exists.
 * Placeholder data lives in localStorage so the UI feels complete.
 */

export type EventKind =
  | "handshake"
  | "page"
  | "action"
  | "page_blocked"
  | "action_blocked"
  | "handshake_denied";

export interface AgentEvent {
  id: string;
  time: string;
  agentId: string;
  kind: EventKind;
  target: string;
}

export interface Endpoint {
  id: string;
  label: string;
  kind: "page" | "action";
  ref: string;
  agentAccess: boolean;
}

export interface Site {
  id: string;
  name: string;
  url: string;
  siteKey: string;
  welcome: string;
  blockedAgents: string;
  endpoints: Endpoint[];
  events: AgentEvent[];
}

interface State {
  user: { email: string } | null;
  activeSiteId: string;
  sites: Site[];
}

const KEY = "aurif-state-v1";

const randKey = () =>
  "ak_live_" +
  Array.from({ length: 28 }, () => "abcdefghijklmnopqrstuvwxyz0123456789"[Math.floor(Math.random() * 36)]).join("");

function endpoints(): Endpoint[] {
  const e = (id: string, label: string, kind: "page" | "action", ref: string, on = true): Endpoint => ({
    id, label, kind, ref, agentAccess: on,
  });
  return [
    e("p-home", "Home page", "page", "/"),
    e("p-shop", "Shop", "page", "/products"),
    e("p-product", "Product pages", "page", "/products/:slug"),
    e("p-cart", "Cart page", "page", "/cart", false),
    e("a-shop", "Shop", "action", "nav.shop"),
    e("a-cart", "Cart", "action", "nav.cart"),
    e("a-home", "Home", "action", "nav.home"),
    e("a-tote", "Add Field Tote", "action", "cart.add.field_tote"),
    e("a-notebook", "Add Trail Notebook", "action", "cart.add.trail_notebook"),
    e("a-clear", "Clear cart", "action", "cart.clear", false),
    e("a-checkout", "Checkout", "action", "cart.checkout", false),
  ];
}

function events(): AgentEvent[] {
  const now = Date.now();
  const rows: [string, EventKind, string][] = [
    ["openai-operator/1.2", "handshake", "scopes=view+act"],
    ["openai-operator/1.2", "page", "/"],
    ["openai-operator/1.2", "page", "/products"],
    ["openai-operator/1.2", "action", "cart.add.field_tote"],
    ["openai-operator/1.2", "action_blocked", "cart.checkout"],
    ["claude-browser/0.9", "handshake", "scopes=view"],
    ["claude-browser/0.9", "page", "/products/trail-notebook"],
    ["claude-browser/0.9", "page_blocked", "/cart"],
    ["scrapy-gpt/0.1", "handshake_denied", "agent blocked by owner"],
    ["perplexity-agent/2.0", "handshake", "scopes=view"],
    ["perplexity-agent/2.0", "page", "/"],
  ];
  return rows
    .map(([agentId, kind, target], i) => ({
      id: `ev-${i}`,
      time: new Date(now - (rows.length - i) * 7 * 60_000).toISOString(),
      agentId, kind, target,
    }))
    .reverse();
}

function seed(): State {
  return {
    user: null,
    activeSiteId: "site-1",
    sites: [
      {
        id: "site-1", name: "Fieldhouse Goods", url: "https://fieldhouse.shop", siteKey: randKey(),
        welcome: "Welcome to Fieldhouse Goods. Durable carry for long walks.",
        blockedAgents: "scrapy-gpt/0.1", endpoints: endpoints(), events: events(),
      },
      {
        id: "site-2", name: "Fieldhouse Journal", url: "https://journal.fieldhouse.shop", siteKey: randKey(),
        welcome: "Field notes and gear stories from the Fieldhouse team.",
        blockedAgents: "", endpoints: endpoints().slice(0, 3), events: [],
      },
    ],
  };
}

let state: State | null = null;
const listeners = new Set<() => void>();
const SERVER: State = seed();

function load(): State {
  if (state) return state;
  if (typeof window === "undefined") return SERVER;
  try {
    const raw = localStorage.getItem(KEY);
    state = raw ? (JSON.parse(raw) as State) : seed();
  } catch {
    state = seed();
  }
  return state;
}

function set(updater: (s: State) => State) {
  state = updater(load());
  localStorage.setItem(KEY, JSON.stringify(state));
  listeners.forEach((l) => l());
}

export function useAurif<T>(select: (s: State) => T): T {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    () => select(load()),
    () => select(SERVER),
  );
}

export const getState = load;

const patchSite = (id: string, fn: (s: Site) => Site) =>
  set((s) => ({ ...s, sites: s.sites.map((x) => (x.id === id ? fn(x) : x)) }));

// API hook (auth): POST /api/auth/login
export function login(email: string, password: string): string | null {
  if (!email.includes("@") || password.length < 6) return "Enter a valid email and a password of 6+ characters.";
  if (email === "owner@aurif.dev" && password !== "demo1234") return "Incorrect password.";
  set((s) => ({ ...s, user: { email } }));
  return null;
}
// API hook (auth): POST /api/auth/signup
export const signup = login;
// API hook (auth): POST /api/auth/logout
export const logout = () => set((s) => ({ ...s, user: null }));

// API hook (sites): GET /api/sites
export const setActiveSite = (id: string) => set((s) => ({ ...s, activeSiteId: id }));
// API hook (sites): PATCH /api/sites/:id
export const updateSite = (id: string, data: Partial<Pick<Site, "name" | "url" | "welcome" | "blockedAgents">>) =>
  patchSite(id, (s) => ({ ...s, ...data }));
// API hook (sites): POST /api/sites/:id/rotate-key
export const rotateKey = (id: string) => patchSite(id, (s) => ({ ...s, siteKey: randKey() }));

// API hook (endpoints): PATCH /api/sites/:id/endpoints/:endpointId { agent_access }
export const toggleEndpoint = (siteId: string, endpointId: string, on: boolean) =>
  patchSite(siteId, (s) => ({
    ...s,
    endpoints: s.endpoints.map((e) => (e.id === endpointId ? { ...e, agentAccess: on } : e)),
  }));

// API hook (activity): POST (written server-side by the Aurif edge when agents call AI endpoints)
export const logEvent = (siteId: string, ev: Omit<AgentEvent, "id" | "time">) =>
  patchSite(siteId, (s) => ({
    ...s,
    events: [{ ...ev, id: crypto.randomUUID(), time: new Date().toISOString() }, ...s.events],
  }));

export const useActiveSite = () =>
  useAurif((s) => s.sites.find((x) => x.id === s.activeSiteId) ?? s.sites[0]);

export const isBlockedKind = (k: EventKind) => k.endsWith("_blocked") || k === "handshake_denied";
