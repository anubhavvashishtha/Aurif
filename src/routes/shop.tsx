import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/shop")({
  validateSearch: (s: Record<string, unknown>) => ({ q: typeof s.q === "string" ? s.q : undefined }),
  head: () => ({ meta: [{"title": "Shop \u2014 Northline Goods"}, {"name": "description", "content": "Explore all Northline Goods bags, notebooks and field tools."}, {"property": "og:title", "content": "Shop \u2014 Northline Goods"}, {"property": "og:description", "content": "Explore all Northline Goods bags, notebooks and field tools."}, {"property": "og:type", "content": "website"}, {"name": "twitter:card", "content": "summary_large_image"}] }),
  component: () => <main className="mx-auto max-w-7xl px-8 py-16"><h1 className="text-4xl">Coming soon</h1></main>,
});
