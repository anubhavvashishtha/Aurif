import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/bags")({
  validateSearch: (s: Record<string, unknown>): { q?: string } => typeof s["q"] === "string" ? { q: s["q"] } : {},
  head: () => ({ meta: [{"title": "Bags \u2014 Northline Goods"}, {"name": "description", "content": "Explore canvas totes, weekend duffels and waxed caps."}, {"property": "og:title", "content": "Bags \u2014 Northline Goods"}, {"property": "og:description", "content": "Explore canvas totes, weekend duffels and waxed caps."}, {"property": "og:type", "content": "website"}, {"name": "twitter:card", "content": "summary_large_image"}] }),
  component: () => <main className="mx-auto max-w-7xl px-8 py-16"><h1 className="text-4xl">Coming soon</h1></main>,
});
