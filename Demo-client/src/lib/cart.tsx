import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getProduct } from "./catalog";

export type CartLine = {
  id: string; // slug + variant key
  slug: string;
  variant: Record<string, string>;
  qty: number;
};

export type Order = {
  number: string;
  email: string;
  name: string;
  lines: (CartLine & { name: string; price: number; image: string })[];
  total: number;
  method: string;
};

type CartCtx = {
  lines: CartLine[];
  count: number;
  promo: string | null;
  setPromo: (c: string | null) => void;
  add: (slug: string, variant: Record<string, string>, qty?: number) => void;
  setQty: (id: string, qty: number) => void;
  remove: (id: string) => void;
  clear: () => void;
  lastAdded: number;
};

const Ctx = createContext<CartCtx | null>(null);
const KEY = "northline-cart-v1";
const API_BASE = import.meta.env.VITE_AURIF_API ?? "http://127.0.0.1:8787";

export const lineId = (slug: string, variant: Record<string, string>) =>
  slug + "|" + Object.entries(variant).map(([k, v]) => `${k}:${v}`).join(",");

function knownLines(raw: unknown): CartLine[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((line): line is CartLine => {
    if (!line || typeof line !== "object") return false;
    const row = line as CartLine;
    return Boolean(row.slug && row.id && getProduct(row.slug) && row.qty > 0);
  });
}

function linesKey(lines: CartLine[]) {
  return JSON.stringify(lines.map((line) => ({ id: line.id, slug: line.slug, variant: line.variant, qty: line.qty })));
}

async function readShopCart(): Promise<CartLine[] | null> {
  try {
    const res = await fetch(`${API_BASE}/api/public/shop-cart`);
    if (!res.ok) return null;
    const data = (await res.json()) as { lines?: unknown };
    return knownLines(data.lines);
  } catch {
    return null;
  }
}

function writeShopCart(lines: CartLine[]) {
  void fetch(`${API_BASE}/api/public/shop-cart`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lines }),
  }).catch(() => {});
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>([]);
  const [promo, setPromo] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [lastAdded, setLastAdded] = useState(0);
  const serverLines = useRef("[]");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let local: CartLine[] = [];
      let savedPromo: string | null = null;
      try {
        const raw = localStorage.getItem(KEY);
        if (raw) {
          const saved = JSON.parse(raw);
          local = knownLines(saved.lines);
          savedPromo = saved.promo ?? null;
        }
      } catch {
        /* keep the empty cart */
      }
      const remote = await readShopCart();
      if (cancelled) return;
      if (remote && remote.length) {
        serverLines.current = linesKey(remote);
        setLines(remote);
      } else if (remote && local.length) {
        serverLines.current = linesKey(local);
        setLines(local);
        writeShopCart(local);
      } else if (remote) {
        serverLines.current = "[]";
        setLines([]);
      } else {
        setLines(local);
      }
      setPromo(savedPromo);
      setLoaded(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!loaded) return;
    localStorage.setItem(KEY, JSON.stringify({ lines, promo }));
    const key = linesKey(lines);
    if (key === serverLines.current) return;
    serverLines.current = key;
    writeShopCart(lines);
  }, [lines, promo, loaded]);

  useEffect(() => {
    if (!loaded) return;
    const timer = window.setInterval(async () => {
      const remote = await readShopCart();
      if (!remote) return;
      const key = linesKey(remote);
      if (key === serverLines.current) return;
      serverLines.current = key;
      setLines(remote);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [loaded]);

  const value = useMemo<CartCtx>(
    () => ({
      lines,
      promo,
      setPromo,
      lastAdded,
      count: lines.reduce((s, l) => s + l.qty, 0),
      add: (slug, variant, qty = 1) => {
        const id = lineId(slug, variant);
        setLines((ls) => {
          const ex = ls.find((l) => l.id === id);
          if (ex) return ls.map((l) => (l.id === id ? { ...l, qty: Math.min(10, l.qty + qty) } : l));
          return [...ls, { id, slug, variant, qty }];
        });
        setLastAdded(Date.now());
      },
      setQty: (id, qty) =>
        setLines((ls) => ls.map((l) => (l.id === id ? { ...l, qty: Math.max(1, Math.min(10, qty)) } : l))),
      remove: (id) => setLines((ls) => ls.filter((l) => l.id !== id)),
      clear: () => {
        setLines([]);
        setPromo(null);
      },
    }),
    [lines, promo, lastAdded],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCart() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useCart outside provider");
  return c;
}

export const defaultVariant = (slug: string) => {
  const p = getProduct(slug);
  return Object.fromEntries((p?.variants ?? []).map((v) => [v.name, v.options[0] ?? ""])) as Record<string, string>;
};

export const ORDER_KEY = "northline-last-order";
