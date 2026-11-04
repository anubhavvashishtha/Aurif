import { Collection } from "@/components/shop/Collection";
import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/tools")({
  validateSearch: (s: Record<string, unknown>): { q?: string } => typeof s["q"] === "string" ? { q: s["q"] } : {},
  head: () => ({ meta: [{"title": "Field tools \u2014 Northline Goods"}, {"name": "description", "content": "Explore pocket knives, camp mugs and repair kits."}, {"property": "og:title", "content": "Field tools \u2014 Northline Goods"}, {"property": "og:description", "content": "Explore pocket knives, camp mugs and repair kits."}, {"property": "og:type", "content": "website"}, {"name": "twitter:card", "content": "summary_large_image"}] }),
  component: () => <Collection category="tools" />,
});
