import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
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

export const lineId = (slug: string, variant: Record<string, string>) =>
  slug + "|" + Object.entries(variant).map(([k, v]) => `${k}:${v}`).join(",");

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>([]);
  const [promo, setPromo] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [lastAdded, setLastAdded] = useState(0);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) {
        const d = JSON.parse(raw);
        setLines((d.lines ?? []).filter((l: CartLine) => getProduct(l.slug)));
        setPromo(d.promo ?? null);
      }
    } catch {}
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (loaded) localStorage.setItem(KEY, JSON.stringify({ lines, promo }));
  }, [lines, promo, loaded]);

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
  return Object.fromEntries((p?.variants ?? []).map((v) => [v.name, v.options[0]]));
};

export const ORDER_KEY = "northline-last-order";
