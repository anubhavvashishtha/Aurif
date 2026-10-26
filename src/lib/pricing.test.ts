import { describe, expect, it } from "vitest";
import { computeTotals } from "./pricing";

describe("cart pricing", () => {
  it("NORTH10 takes 10% off the subtotal", () => {
    const t = computeTotals([{ price: 50, qty: 1 }], "north10");
    expect(t.promoDiscount).toBe(5);
    expect(t.total).toBe(53); // 50 - 5 + 8 shipping
  });
  it("unknown promo codes give no discount", () => {
    expect(computeTotals([{ price: 50, qty: 1 }], "SAVE50").promoDiscount).toBe(0);
  });
  it("standard shipping is free from $100", () => {
    expect(computeTotals([{ price: 100, qty: 1 }], null).shipping).toBe(0);
    expect(computeTotals([{ price: 99, qty: 1 }], null).shipping).toBe(8);
  });
  it("reports sale savings from compare-at prices", () => {
    expect(computeTotals([{ price: 68, compareAt: 85, qty: 2 }], null).saleSavings).toBe(34);
  });
});
