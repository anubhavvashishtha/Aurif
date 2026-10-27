import { createFileRoute } from "@tanstack/react-router";
import { products, formatUSD } from "@/lib/catalog";
export const Route = createFileRoute("/")({
  head: () => ({ meta: [
    { title: "Northline Goods — Everyday field goods" },
    { name: "description", content: "Explore Northline canvas bags, notebooks and field tools." },
    { property: "og:title", content: "Northline Goods — Everyday field goods" },
    { property: "og:description", content: "Explore Northline canvas bags, notebooks and field tools." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: Index,
});

function Index() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-12 md:px-8">
      <h1 className="text-4xl text-foreground">Northline Goods</h1>
      <p className="mt-3 text-muted-foreground">Bags, notebooks and field tools.</p>
      <div className="mt-10 grid grid-cols-2 gap-x-6 gap-y-10 lg:grid-cols-4">
        {products.map((product) => (
          <article key={product.slug}>
            <img src={product.images[0]?.src} alt={product.name} width={1024} height={1024} className="aspect-square w-full rounded-md object-cover" />
            <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-xl">{product.name}</h2>
              <span className="text-sm">{formatUSD(product.price)}</span>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{product.tagline}</p>
          </article>
        ))}
      </div>
    </main>
  );
}
