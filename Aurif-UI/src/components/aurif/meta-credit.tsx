import type { MetaModelRef } from "@/lib/aurif-store";

export function metaModelLabel(model?: MetaModelRef | string | null) {
  if (!model) return "Muse";
  if (typeof model === "string") return model;
  return model.label || model.id || "Muse";
}

export function MetaCredit({
  model,
  latencyMs,
  degraded,
  fallback,
  warning,
}: {
  model?: MetaModelRef | string | null;
  latencyMs?: number | null;
  degraded?: boolean;
  fallback?: string | null;
  warning?: string | null;
}) {
  const label = metaModelLabel(model);
  const latency = typeof latencyMs === "number" ? `${latencyMs} ms` : null;
  const usingFallback = Boolean(degraded || fallback);
  return (
    <div className="space-y-1">
      {degraded && (
        <p className="text-sm text-destructive">
          {warning || "Meta model unavailable. Showing the fallback result."}
        </p>
      )}
      {!degraded && fallback && (
        <p className="text-sm text-muted-foreground">{warning || "Showing the fallback result."}</p>
      )}
      <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
        Powered by Meta {label}
        {latency ? ` · ${latency}` : ""}
        {usingFallback ? " · fallback" : ""}
      </p>
    </div>
  );
}
