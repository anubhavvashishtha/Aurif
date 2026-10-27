import { Collection } from "@/components/shop/Collection";
import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/notebooks")({
  validateSearch: (s: Record<string, unknown>): { q?: string } => typeof s["q"] === "string" ? { q: s["q"] } : {},
  head: () => ({ meta: [{"title": "Notebooks \u2014 Northline Goods"}, {"name": "description", "content": "Explore pocket notebooks and clothbound sketchbooks."}, {"property": "og:title", "content": "Notebooks \u2014 Northline Goods"}, {"property": "og:description", "content": "Explore pocket notebooks and clothbound sketchbooks."}, {"property": "og:type", "content": "website"}, {"name": "twitter:card", "content": "summary_large_image"}] }),
  component: () => <Collection category="notebooks" />,
});
