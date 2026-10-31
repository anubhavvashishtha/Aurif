import type { MetaModelRef } from "@/lib/aurif-store";

export function metaModelLabel(model?: MetaModelRef | string | null) {
  if (!model) return "Muse";
  if (typeof model === "string") return model;
  return model.label || model.id || "Muse";
}

function looksNonMeta(value: string) {
  return /deepseek|gpt-|claude|gemini|qwen|grok/i.test(value);
}

/** Credit line. Meta models keep the Meta prefix. DeepSeek never gets it. */
export function poweredByLine(model?: MetaModelRef | string | null) {
  if (!model) return "Powered by Meta Muse";
  if (typeof model === "string") {
    return looksNonMeta(model) ? `Powered by ${model}` : `Powered by Meta ${model}`;
  }
  if (model.powered_by) return `Powered by ${model.powered_by}`;
  const label = model.label || model.id || "Muse";
  const blob = `${model.id || ""} ${model.label || ""} ${model.provider || ""} ${model.family || ""}`;
  if ((model.family && model.family !== "meta") || looksNonMeta(blob)) return `Powered by ${label}`;
  return `Powered by Meta ${label}`;
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
  const latency = typeof latencyMs === "number" ? `${latencyMs} ms` : null;
  const usingFallback = Boolean(degraded || fallback);
  const metaFamily =
    !model || typeof model === "string" ? !model || !looksNonMeta(model) : !model.family || model.family === "meta";
  return (
    <div className="space-y-1">
      {degraded && (
        <p className="text-sm text-destructive">
          {warning ||
            (metaFamily
              ? "Meta model unavailable. Showing the fallback result."
              : "Model unavailable. Showing the fallback result.")}
        </p>
      )}
      {!degraded && fallback && (
        <p className="text-sm text-muted-foreground">{warning || "Showing the fallback result."}</p>
      )}
      <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
        {poweredByLine(model)}
        {latency ? ` · ${latency}` : ""}
        {usingFallback ? " · fallback" : ""}
      </p>
    </div>
  );
}
