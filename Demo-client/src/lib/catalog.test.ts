import { describe, expect, it } from "vitest";
import data from "./catalog.json";
import { getProduct, products } from "./catalog";

describe("Static JSON catalog", () => {
  it("exposes every JSON product without changing its data", () => {
    expect(products.length).toBe(data.products.length);
    for (const entry of data.products) {
      const product = getProduct(entry.slug);
      expect(product).toBeDefined();
      expect(product?.price).toBe(entry.price);
      expect(product?.reviews).toEqual(entry.reviews);
      expect(product?.variants).toEqual(entry.variants);
      expect(product?.images.every((image) => image.src.length > 0)).toBe(true);
    }
  });
});