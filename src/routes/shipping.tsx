import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/shipping")({
  validateSearch: (s: Record<string, unknown>): { q?: string } => typeof s["q"] === "string" ? { q: s["q"] } : {},
  head: () => ({ meta: [{"title": "Shipping and returns \u2014 Northline Goods"}, {"name": "description", "content": "Shipping and returns information for Northline Goods."}, {"property": "og:title", "content": "Shipping and returns \u2014 Northline Goods"}, {"property": "og:description", "content": "Shipping and returns information for Northline Goods."}, {"property": "og:type", "content": "website"}, {"name": "twitter:card", "content": "summary_large_image"}] }),
  component: () => <main className="mx-auto max-w-7xl px-8 py-16"><h1 className="text-4xl">Coming soon</h1></main>,
});
