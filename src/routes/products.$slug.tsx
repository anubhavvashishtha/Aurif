import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/products/$slug")({
  head: () => ({ meta: [{"title": "Product \u2014 Northline Goods"}, {"name": "description", "content": "Discover product details from the Northline Goods catalog."}, {"property": "og:title", "content": "Product \u2014 Northline Goods"}, {"property": "og:description", "content": "Discover product details from the Northline Goods catalog."}, {"property": "og:type", "content": "website"}, {"name": "twitter:card", "content": "summary_large_image"}] }),
  component: () => <main className="mx-auto max-w-7xl px-8 py-16"><h1 className="text-4xl">Coming soon</h1></main>,
});
