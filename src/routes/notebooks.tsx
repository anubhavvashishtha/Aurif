import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/notebooks")({
  validateSearch: (s: Record<string, unknown>) => ({ q: typeof s.q === "string" ? s.q : undefined }),
  head: () => ({ meta: [{"title": "Notebooks \u2014 Northline Goods"}, {"name": "description", "content": "Explore pocket notebooks and clothbound sketchbooks."}, {"property": "og:title", "content": "Notebooks \u2014 Northline Goods"}, {"property": "og:description", "content": "Explore pocket notebooks and clothbound sketchbooks."}, {"property": "og:type", "content": "website"}, {"name": "twitter:card", "content": "summary_large_image"}] }),
  component: () => <main className="mx-auto max-w-7xl px-8 py-16"><h1 className="text-4xl">Coming soon</h1></main>,
});
