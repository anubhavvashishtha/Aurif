import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { discountPct, type Product } from "@/lib/catalog";
import { defaultVariant, useCart } from "@/lib/cart";
import { DiscountBadge, Price, RatingStars } from "./bits";

export function ProductCard({ product }: { product: Product }) {
  const { add } = useCart();
  const pct = discountPct(product);
  return (
    <div className="group flex flex-col">
      <Link
        to="/products/$slug"
        params={{ slug: product.slug }}
        className="relative block aspect-[4/5] overflow-hidden rounded-md bg-muted"
      >
        <img
          src={product.images[0]?.src}
          alt={product.name}
          loading="lazy"
          width={1024}
          height={1024}
          className="h-full w-full animate-softfade object-cover transition-transform duration-700 group-hover:scale-[1.03]"
        />
        <div className="absolute left-3 top-3 flex gap-1.5">
          <DiscountBadge pct={pct} />
          {product.stock === "low" && (
            <span className="rounded-sm bg-background/90 px-1.5 py-0.5 text-[0.68rem] font-medium">
              Only {product.stockLeft} left
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            add(product.slug, defaultVariant(product.slug));
            toast.success(`${product.name} added to cart`);
          }}
          className="absolute inset-x-3 bottom-3 translate-y-2 rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground opacity-0 transition-all group-hover:translate-y-0 group-hover:opacity-100 max-md:translate-y-0 max-md:opacity-100"
        >
          Quick add
        </button>
      </Link>
      <div className="mt-3 flex items-start justify-between gap-3">
        <Link to="/products/$slug" params={{ slug: product.slug }} className="font-display text-lg leading-tight hover:underline">
          {product.name}
        </Link>
        <Price price={product.price} compareAt={product.compareAt} />
      </div>
      <div className="mt-1.5">
        <RatingStars rating={product.rating} count={product.reviewCount} />
      </div>
    </div>
  );
}
