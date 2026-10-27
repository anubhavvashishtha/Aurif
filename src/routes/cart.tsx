import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/cart")({
  validateSearch: (s: Record<string, unknown>) => ({ q: typeof s.q === "string" ? s.q : undefined }),
  head: () => ({ meta: [{"title": "Your cart \u2014 Northline Goods"}, {"name": "description", "content": "Review your Northline Goods selections."}, {"property": "og:title", "content": "Your cart \u2014 Northline Goods"}, {"property": "og:description", "content": "Review your Northline Goods selections."}, {"property": "og:type", "content": "website"}, {"name": "twitter:card", "content": "summary_large_image"}] }),
  component: () => <main className="mx-auto max-w-7xl px-8 py-16"><h1 className="text-4xl">Coming soon</h1></main>,
});
