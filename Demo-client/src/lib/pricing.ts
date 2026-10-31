export type PricedLine = { price: number; compareAt?: number; qty: number };
export type ShippingMethod = "standard" | "express";

export const FREE_SHIPPING_THRESHOLD = 100;
export const SHIPPING_RATES: Record<ShippingMethod, number> = { standard: 8, express: 18 };
export const PROMO_CODES: Record<string, number> = { NORTH10: 0.1 };

export const normalizePromo = (code: string) => code.trim().toUpperCase();
export const isValidPromo = (code: string) => normalizePromo(code) in PROMO_CODES;

const round = (n: number) => Math.round(n * 100) / 100;

export function computeTotals(
  lines: PricedLine[],
  promo: string | null,
  method: ShippingMethod = "standard",
) {
  const subtotal = round(lines.reduce((s, l) => s + l.price * l.qty, 0));
  const saleSavings = round(
    lines.reduce((s, l) => s + (l.compareAt && l.compareAt > l.price ? (l.compareAt - l.price) * l.qty : 0), 0),
  );
  const rate = promo ? (PROMO_CODES[normalizePromo(promo)] ?? 0) : 0;
  const promoDiscount = round(subtotal * rate);
  const shipping =
    subtotal === 0
      ? 0
      : method === "standard" && subtotal >= FREE_SHIPPING_THRESHOLD
        ? 0
        : SHIPPING_RATES[method];
  const total = round(subtotal - promoDiscount + shipping);
  return { subtotal, saleSavings, promoDiscount, shipping, total };
}
