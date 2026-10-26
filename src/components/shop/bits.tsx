import { Star } from "lucide-react";
import { cn } from "@/lib/utils";
import { discountPct, formatUSD } from "@/lib/catalog";

export function RatingStars({
  rating,
  count,
  size = "sm",
}: {
  rating: number;
  count?: number;
  size?: "sm" | "md";
}) {
  const s = size === "sm" ? "size-3.5" : "size-4.5";
  return (
    <div className="flex items-center gap-1.5" aria-label={`${rating} out of 5 stars`}>
      <div className="flex">
        {[1, 2, 3, 4, 5].map((i) => {
          const fill = Math.max(0, Math.min(1, rating - (i - 1)));
          return (
            <span key={i} className={cn("relative inline-block", s)}>
              <Star className={cn("absolute inset-0 text-border", s)} fill="currentColor" strokeWidth={0} />
              <span className="absolute inset-0 overflow-hidden" style={{ width: `${fill * 100}%` }}>
                <Star className={cn("text-star", s)} fill="currentColor" strokeWidth={0} />
              </span>
            </span>
          );
        })}
      </div>
      {count !== undefined && (
        <span className="text-xs text-muted-foreground">
          {rating.toFixed(1)} ({count})
        </span>
      )}
    </div>
  );
}

export function Price({
  price,
  compareAt,
  size = "sm",
}: {
  price: number;
  compareAt?: number;
  size?: "sm" | "lg";
}) {
  const pct = discountPct({ price, compareAt });
  return (
    <div className="flex flex-wrap items-baseline gap-2">
      <span className={cn("font-medium", size === "lg" ? "text-2xl" : "text-sm", pct && "text-sale")}>
        {formatUSD(price)}
      </span>
      {pct > 0 && (
        <>
          <span className={cn("text-muted-foreground line-through", size === "lg" ? "text-base" : "text-xs")}>
            {formatUSD(compareAt!)}
          </span>
          {size === "lg" && <DiscountBadge pct={pct} />}
        </>
      )}
    </div>
  );
}

export function DiscountBadge({ pct, className }: { pct: number; className?: string }) {
  if (!pct) return null;
  return (
    <span
      className={cn(
        "inline-block rounded-sm bg-sale px-1.5 py-0.5 text-[0.68rem] font-semibold tracking-wide text-sale-foreground",
        className,
      )}
    >
      −{pct}%
    </span>
  );
}

export function StockNote({ stock, left }: { stock: "in" | "low" | "out"; left?: number }) {
  if (stock === "out") return <span className="text-sm text-destructive">Out of stock</span>;
  if (stock === "low") return <span className="text-sm text-sale">● Only {left} left</span>;
  return <span className="text-sm text-success">● In stock</span>;
}

export function QtyStepper({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="inline-flex h-10 items-center rounded-md border border-input">
      <button
        type="button"
        aria-label="Decrease quantity"
        className="h-full w-9 text-lg hover:bg-muted"
        onClick={() => onChange(value - 1)}
      >
        −
      </button>
      <span className="w-8 text-center text-sm tabular-nums">{value}</span>
      <button
        type="button"
        aria-label="Increase quantity"
        className="h-full w-9 text-lg hover:bg-muted"
        onClick={() => onChange(value + 1)}
      >
        +
      </button>
    </div>
  );
}
