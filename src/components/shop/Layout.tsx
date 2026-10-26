import { Link, useNavigate } from "@tanstack/react-router";
import { Menu, Search, ShoppingBag, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useCart } from "@/lib/cart";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/shop", label: "Shop" },
  { to: "/bags", label: "Bags" },
  { to: "/notebooks", label: "Notebooks" },
  { to: "/tools", label: "Tools" },
] as const;

export function Header() {
  const { count, lastAdded } = useCart();
  const [pop, setPop] = useState(false);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    if (!lastAdded) return;
    setPop(true);
    const t = setTimeout(() => setPop(false), 500);
    return () => clearTimeout(t);
  }, [lastAdded]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    navigate({ to: "/shop", search: { q: q || undefined } });
    setOpen(false);
  };

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
      <div className="bg-ink py-1.5 text-center text-xs tracking-wide text-ink-foreground">
        Free shipping over $100 · Free returns within 30 days
      </div>
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4 md:px-8">
        <button className="md:hidden" aria-label="Menu" onClick={() => setOpen((o) => !o)}>
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
        <Link to="/" className="font-display text-2xl tracking-tight">
          Northline
        </Link>
        <nav className="hidden items-center gap-6 md:flex">
          {nav.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              activeProps={{ className: "text-foreground" }}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <form onSubmit={submit} className="ml-auto hidden items-center gap-2 rounded-md border border-input bg-card px-3 md:flex">
          <Search className="size-4 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search goods"
            className="h-9 w-44 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </form>
        <Link to="/cart" className="relative ml-auto md:ml-0" aria-label={`Cart, ${count} items`}>
          <ShoppingBag className="size-5" />
          {count > 0 && (
            <span
              className={cn(
                "absolute -right-2 -top-2 flex size-4.5 items-center justify-center rounded-full bg-accent text-[0.65rem] font-semibold text-accent-foreground",
                pop && "animate-pop",
              )}
            >
              {count}
            </span>
          )}
        </Link>
      </div>
      {open && (
        <div className="border-t border-border px-4 pb-4 md:hidden">
          <form onSubmit={submit} className="mt-3 flex items-center gap-2 rounded-md border border-input bg-card px-3">
            <Search className="size-4 text-muted-foreground" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search goods" className="h-10 flex-1 bg-transparent text-sm outline-none" />
          </form>
          <nav className="mt-3 flex flex-col">
            {nav.map((n) => (
              <Link key={n.to} to={n.to} onClick={() => setOpen(false)} className="border-b border-border py-3 font-display text-lg">
                {n.label}
              </Link>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}

export function Footer() {
  return (
    <footer className="mt-24 bg-ink text-ink-foreground">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 md:grid-cols-4 md:px-8">
        <div className="md:col-span-2">
          <p className="font-display text-3xl">Northline Goods</p>
          <p className="mt-3 max-w-sm text-sm opacity-70">Gear for slow weekends. Made in small batches and shipped from Portland, Oregon.</p>
        </div>
        <div className="flex flex-col gap-2 text-sm">
          <p className="mb-1 text-xs uppercase tracking-[0.18em] opacity-60">Shop</p>
          <Link to="/bags" className="opacity-80 hover:opacity-100">Bags</Link>
          <Link to="/notebooks" className="opacity-80 hover:opacity-100">Notebooks</Link>
          <Link to="/tools" className="opacity-80 hover:opacity-100">Field Tools</Link>
        </div>
        <div className="flex flex-col gap-2 text-sm">
          <p className="mb-1 text-xs uppercase tracking-[0.18em] opacity-60">Help</p>
          <Link to="/about" className="opacity-80 hover:opacity-100">About</Link>
          <Link to="/shipping" className="opacity-80 hover:opacity-100">Shipping</Link>
          <Link to="/shipping" hash="returns" className="opacity-80 hover:opacity-100">Returns</Link>
          <a href="mailto:hello@northlinegoods.com" className="opacity-80 hover:opacity-100">Contact</a>
        </div>
      </div>
      <div className="border-t border-ink-foreground/10 py-5 text-center text-xs opacity-60">© {2026} Northline Goods</div>
    </footer>
  );
}
