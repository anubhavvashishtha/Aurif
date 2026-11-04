import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowRight, ShoppingBag } from "lucide-react";
import { useCart } from "@/lib/cart";
import { formatUSD, getProduct } from "@/lib/catalog";
import { computeTotals } from "@/lib/pricing";
import { OrderSummary } from "@/components/shop/OrderSummary";
import { Button } from "@/components/ui/button";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/checkout")({
  head: () =>
    pageHead(
      "Checkout",
      "Demo checkout for Northline Goods. No payment is processed.",
    ),
  component: Checkout,
});

type PlacedOrder = {
  names: string[];
  total: string;
};

function Checkout() {
  const { lines, promo, clear } = useCart();
  const [placed, setPlaced] = useState<PlacedOrder | null>(null);
  const [refused, setRefused] = useState(false);

  const priced = lines.flatMap((line) => {
    const product = getProduct(line.slug);
    return product ? [{ price: product.price, compareAt: product.compareAt, qty: line.qty }] : [];
  });
  const totals = computeTotals(priced, promo);

  const placeOrder = () => {
    if (!lines.length) {
      setRefused(true);
      return;
    }
    const names = lines.flatMap((line) => {
      const product = getProduct(line.slug);
      return product ? [`${product.name} × ${line.qty}`] : [];
    });
    setPlaced({ names, total: formatUSD(totals.total) });
    clear();
  };

  if (placed) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-14 md:px-8">
        <p className="eyebrow">Demo checkout</p>
        <h1 className="mt-4 text-5xl">Demo checkout complete</h1>
        <p className="mt-5 max-w-xl leading-relaxed text-muted-foreground">
          No payment processed. This is a demonstration order, not a charge.
        </p>
        <ul className="mt-8 space-y-2 border-y border-border py-5 text-sm">
          {placed.names.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
        <p className="mt-4 text-lg font-medium">Total {placed.total}</p>
        <Button asChild className="mt-8">
          <Link to="/shop">
            Continue shopping
            <ArrowRight />
          </Link>
        </Button>
      </main>
    );
  }

  if (!lines.length || refused) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-14 md:px-8">
        <div className="py-16 text-center">
          <ShoppingBag className="mx-auto size-10 text-muted-foreground" />
          <h1 className="mt-5 text-4xl">Checkout needs something in the cart</h1>
          <p role="alert" className="mx-auto mt-4 max-w-md text-muted-foreground">
            Your cart is empty, so this checkout can't be completed. Add an item first. No payment is taken here.
          </p>
          <Button asChild className="mt-8">
            <Link to="/shop">
              Explore the collection
              <ArrowRight />
            </Link>
          </Button>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-12 md:px-8">
      <p className="eyebrow">Demo checkout</p>
      <h1 className="mt-4 text-5xl">Checkout</h1>
      <p className="mt-4 max-w-xl text-muted-foreground">
        Review the order and place it. This demo does not collect a card or charge anything.
      </p>
      <div className="mt-10 grid gap-12 lg:grid-cols-[1fr_360px]">
        <section>
          <h2 className="text-2xl">No payment</h2>
          <p className="mt-3 max-w-lg leading-relaxed text-muted-foreground">
            Northline's demo checkout confirms the cart and stops there. Nothing is billed, and no card details are asked for.
          </p>
          <Button type="button" size="lg" className="mt-8" onClick={placeOrder}>
            Place demo order
            <ArrowRight />
          </Button>
          <Button asChild variant="link" className="mt-3 px-0">
            <Link to="/cart">Back to cart</Link>
          </Button>
        </section>
        <aside className="self-start border-t border-border pt-6">
          <OrderSummary />
          <p className="mt-4 text-center text-xs text-muted-foreground">No payment processed</p>
        </aside>
      </div>
    </main>
  );
}
