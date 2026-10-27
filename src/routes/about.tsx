import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/about")({
  validateSearch: (s: Record<string, unknown>) => ({ q: typeof s.q === "string" ? s.q : undefined }),
  head: () => ({ meta: [{"title": "About Northline Goods"}, {"name": "description", "content": "The story behind Northline Goods bags, notebooks and field tools."}, {"property": "og:title", "content": "About Northline Goods"}, {"property": "og:description", "content": "The story behind Northline Goods bags, notebooks and field tools."}, {"property": "og:type", "content": "website"}, {"name": "twitter:card", "content": "summary_large_image"}] }),
  component: () => <main className="mx-auto max-w-7xl px-8 py-16"><h1 className="text-4xl">Coming soon</h1></main>,
});
