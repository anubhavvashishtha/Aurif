import { useSyncExternalStore } from "react";
import type { JsonValue, RequestField, ResponseField } from "./aurif-fields";

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
  | "handshake_denied"
  | "field_redacted";

export interface AgentEvent {
  id: string;
  time: string;
  agentId: string;
  kind: EventKind;
  target: string;
  redactedFields?: string[];
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
  const page = (id: string, label: string, ref: string, price: number, on = true): Endpoint => {
    const cart = id === "p-cart";
    const sampleResponse: JsonValue = {
      title: label, summary: "Thoughtful essentials for everyday adventures.",
      elements: [{ label: "Explore collection", action_id: "nav.products" }],
      meta: cart ? { items: 2, products: [{ name: "Field Tote", price: 48 }, { name: "Trail Notebook", price: 16 }] }
        : { name: label, summary: "Made to go further.", price, currency: "USD" },
      rating: 4.8, discount: 10, reviews: [{ author: "Alex", text: "Beautifully made.", rating: 5 }],
    };
    const keys = cart ? ["title", "summary", "elements", "meta", "meta.items", "meta.products", "meta.products[].price", "rating", "discount", "reviews"]
      : ["title", "summary", "elements", "meta", "meta.price", "meta.name", "meta.summary", "rating", "discount", "reviews"];
    return { id, label, kind: "page", ref, agentAccess: on, direction: "read", sampleResponse, sampleRequest: {}, requestFields: [],
      responseFields: keys.map((key) => ({ key, label: key.split(".").at(-1)?.replace("[]", "") ?? key,
        type: /price|rating|discount|items/.test(key) ? "number" : /elements|products|reviews/.test(key) ? "array" : key === "meta" ? "object" : "string",
        agentVisible: !(id === "p-product" && (key === "meta.price" || key === "discount")), })) };
  };
  const action = (id: string, label: string, ref: string, on = true): Endpoint => ({
    id, label, kind: "action", ref, agentAccess: on, direction: "both",
    responseFields: [{ key: "ok", label: "Success", type: "boolean", agentVisible: true }, { key: "summary", label: "Summary", type: "string", agentVisible: true }],
    requestFields: [{ key: "quantity", label: "Quantity", agentAllowed: true }, { key: "args", label: "Action arguments", agentAllowed: true }, { key: "email", label: "Email address", agentAllowed: false }],
    sampleResponse: { ok: true, summary: "Action completed." }, sampleRequest: { quantity: 1, args: { product_id: "widget" }, email: "agent@example.com" },
  });
  return [
    page("p-home", "Home page", "/", 48), page("p-shop", "Shop", "/products", 48),
    page("p-product", "Product: Field Tote", "/products/widget", 48),
    page("p-notebook", "Product: Trail Notebook", "/products/badge", 16),
    page("p-cart", "Cart", "/cart", 64, false),
    action("a-shop", "Navigate to products", "nav.products"), action("a-cart", "Navigate to cart", "nav.cart"),
    action("a-tote", "Add Field Tote", "product.add:widget"), action("a-notebook", "Add Trail Notebook", "product.add:badge"),
    action("a-clear", "Clear cart", "cart.clear", false), action("a-checkout", "Checkout", "cart.checkout", false),
  ];
}

function events(): AgentEvent[] {
  const now = Date.now();
  const rows: [string, EventKind, string][] = [
    ["openai-operator/1.2", "handshake", "scopes=view+act"],
    ["openai-operator/1.2", "page", "/"],
    ["openai-operator/1.2", "page", "/products"],
    ["openai-operator/1.2", "action", "product.add:widget"],
    ["openai-operator/1.2", "action_blocked", "cart.checkout"],
    ["claude-browser/0.9", "handshake", "scopes=view"],
    ["claude-browser/0.9", "page", "/products/widget"],
    ["claude-browser/0.9", "field_redacted", "/products/widget"],
    ["claude-browser/0.9", "page_blocked", "/cart"],
    ["scrapy-gpt/0.1", "handshake_denied", "agent blocked by owner"],
    ["perplexity-agent/2.0", "handshake", "scopes=view"],
    ["perplexity-agent/2.0", "page", "/"],
  ];
  return rows
    .map(([agentId, kind, target], i) => ({
      id: `ev-${i}`,
      time: new Date(now - (rows.length - i) * 7 * 60_000).toISOString(),
      agentId, kind, target, ...(kind === "field_redacted" ? { redactedFields: ["meta.price", "discount"] } : {}),
    }))
    .reverse();
}

function seed(): State {
  return {
    user: null,
    activeSiteId: "site-1",
    sites: [
      {
        id: "site-1", name: "Northline Goods", url: "https://northline.example", siteKey: randKey(),
        welcome: "Welcome to Northline Goods. Thoughtful essentials for everyday adventures.",
        blockedAgents: "scrapy-gpt/0.1", endpoints: endpoints(), events: events(),
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
    const saved = raw ? (JSON.parse(raw) as State) : null;
    // Upgrade old demo data while preserving the signed-in owner.
    state = saved?.sites[0]?.endpoints[0]?.responseFields ? saved : { ...seed(), user: saved?.user ?? null };
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

// TODO API: PUT /api/sites/:id/endpoints/:endpointId/fields
export const updateResponseFields = (siteId: string, endpointId: string, update: (fields: ResponseField[]) => ResponseField[]) =>
  patchSite(siteId, (s) => ({ ...s, endpoints: s.endpoints.map((e) => e.id === endpointId ? { ...e, responseFields: update(e.responseFields) } : e) }));
export const updateRequestField = (siteId: string, endpointId: string, key: string, agentAllowed: boolean) =>
  patchSite(siteId, (s) => ({ ...s, endpoints: s.endpoints.map((e) => e.id === endpointId ? { ...e, requestFields: e.requestFields.map((f) => f.key === key ? { ...f, agentAllowed } : f) } : e) }));

// API hook (activity): POST (written server-side by the Aurif edge when agents call AI endpoints)
export const logEvent = (siteId: string, ev: Omit<AgentEvent, "id" | "time">) =>
  patchSite(siteId, (s) => ({
    ...s,
    events: [{ ...ev, id: crypto.randomUUID(), time: new Date().toISOString() }, ...s.events],
  }));

export const useActiveSite = () =>
  useAurif((s) => (s.sites.find((x) => x.id === s.activeSiteId) ?? s.sites[0]) as Site);

export const isBlockedKind = (k: EventKind) => k.endsWith("_blocked") || k === "handshake_denied";
