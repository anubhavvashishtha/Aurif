import { Collection } from "@/components/shop/Collection";
import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/shop")({
  validateSearch: (s: Record<string, unknown>): { q?: string } => typeof s["q"] === "string" ? { q: s["q"] } : {},
  head: () => ({ meta: [{"title": "Shop \u2014 Northline Goods"}, {"name": "description", "content": "Explore all Northline Goods bags, notebooks and field tools."}, {"property": "og:title", "content": "Shop \u2014 Northline Goods"}, {"property": "og:description", "content": "Explore all Northline Goods bags, notebooks and field tools."}, {"property": "og:type", "content": "website"}, {"name": "twitter:card", "content": "summary_large_image"}] }),
  component: Shop,
});
function Shop() { const { q } = Route.useSearch(); return <Collection query={q ?? ""} />; }
