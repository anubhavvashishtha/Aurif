import tote from "@/assets/p-tote.jpg";
import duffel from "@/assets/p-duffel.jpg";
import notebook from "@/assets/p-notebook.jpg";
import sketchbook from "@/assets/p-sketchbook.jpg";
import knife from "@/assets/p-knife.jpg";
import mug from "@/assets/p-mug.jpg";
import cap from "@/assets/p-cap.jpg";
import repair from "@/assets/p-repair.jpg";
import lifestyle from "@/assets/lifestyle.jpg";
import story from "@/assets/story.jpg";

import catalogData from "./catalog.json";

export type CategorySlug = "bags" | "notebooks" | "tools";

export type GalleryImage = { src: string; alt: string; zoom?: boolean };
export type Review = {
  name: string;
  date: string;
  rating: number;
  title: string;
  body: string;
  verified?: boolean;
};
export type VariantGroup = { name: string; options: string[] };

export type Product = {
  slug: string;
  name: string;
  tagline: string;
  description: string[];
  category: CategorySlug;
  price: number;
  compareAt?: number | undefined;
  sku: string;
  rating: number;
  reviewCount: number;
  histogram: [number, number, number, number, number]; // 5★ → 1★ counts
  stock: "in" | "low" | "out";
  stockLeft?: number;
  images: GalleryImage[];
  variants: VariantGroup[];
  highlights: string[];
  specs: Record<string, string>;
  care: string;
  related: string[];
  reviews: Review[];
  featured?: boolean;
};

const assets: Record<string, string> = {
  "p-tote.jpg": tote, "p-duffel.jpg": duffel, "p-notebook.jpg": notebook,
  "p-sketchbook.jpg": sketchbook, "p-knife.jpg": knife, "p-mug.jpg": mug,
  "p-cap.jpg": cap, "p-repair.jpg": repair, "lifestyle.jpg": lifestyle,
};

type CatalogData = {
  categories: { slug: CategorySlug; name: string; intro: string }[];
  products: Product[];
};

const data = catalogData as CatalogData;
export const categories = data.categories;
export const storyImage = story;
export const products: Product[] = data.products.map((product) => ({
  ...product,
  images: product.images.map((image) => {
    const src = assets[image.src];
    if (!src) throw new Error(`Unknown catalog image: ${image.src}`);
    return { ...image, src };
  }),
}));

export const getProduct = (slug: string) => products.find((p) => p.slug === slug);

export const discountPct = (p: { price: number; compareAt?: number | undefined }) =>
  p.compareAt && p.compareAt > p.price ? Math.round((1 - p.price / p.compareAt) * 100) : 0;

export const formatUSD = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
