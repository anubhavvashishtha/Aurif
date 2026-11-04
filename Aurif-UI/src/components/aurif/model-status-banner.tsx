import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { modelStatusBanner, type ModelHealth } from "@/lib/degraded-banner";

/** Shown on every dashboard page. Text and vision failures are named separately. */
export function ModelStatusBanner() {
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/health`);
        const health = (await res.json()) as ModelHealth;
        if (!cancelled) setMessage(modelStatusBanner(health));
      } catch {
        if (!cancelled) setMessage(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!message) return null;
  return (
    <p className="mb-4 border border-ink/20 bg-frost px-3 py-2 text-sm text-ink" role="status">
      {message}
    </p>
  );
}
