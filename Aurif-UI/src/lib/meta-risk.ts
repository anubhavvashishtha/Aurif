export function riskTone(risk: string): "ok" | "danger" | "muted" {
  if (risk === "low") return "ok";
  if (risk === "high") return "danger";
  return "muted";
}
