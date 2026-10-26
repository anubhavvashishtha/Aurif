import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/products/$slug")({
  head: () => ({ meta: [{ title: "Northline Goods — Product" }] }),
  component: () => <main className="mx-auto max-w-7xl px-8 py-16"><h1 className="text-4xl">Coming soon</h1></main>,
});
