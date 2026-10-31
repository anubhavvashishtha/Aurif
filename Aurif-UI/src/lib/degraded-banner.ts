/** Copy for a text-model outage. Matches keyword-rule handshake scoring. */
export const KEYWORD_ACT_COPY =
  "Act is granted only for a clear shopping request. Export, scraping, or collecting every price stays view-only.";

export type ModelHealthSide = {
  degraded?: boolean;
  last_error?: string | null;
  powered_by?: string;
  label?: string;
  provider?: string;
  model?: string;
};

export type ModelHealth = {
  ok?: boolean;
  degraded?: boolean;
  partial?: boolean;
  text?: ModelHealthSide;
  vision?: ModelHealthSide;
};

function sideName(side: ModelHealthSide | undefined, fallback: string): string {
  return side?.powered_by || side?.label || side?.model || fallback;
}

function visionPhrase(side: ModelHealthSide | undefined): string {
  const powered = sideName(side, "the vision model");
  if ((side?.provider || "").toLowerCase() === "modal") {
    const base = powered.replace(/\s*\(Modal\)\s*$/i, "").trim();
    return `${base} via Modal`;
  }
  return powered;
}

function cause(error: string | null | undefined): string {
  const text = (error || "").trim();
  if (!text) return "";
  const status = text.match(/\b(401|403|404)\b/);
  if (status) return status[1];
  const stripped = text.replace(/^vision model [^:]+:\s*/i, "").trim();
  return stripped.length > 120 ? `${stripped.slice(0, 117)}...` : stripped;
}

/** Per-model banner. Vision-only failures do not claim the handshake left the model. */
export function modelStatusBanner(health: ModelHealth | null | undefined): string | null {
  const textDown = Boolean(health?.text?.degraded);
  const visionDown = Boolean(health?.vision?.degraded);
  if (!textDown && !visionDown) return null;

  const textName = sideName(health?.text, "the text model");
  const visionName = visionPhrase(health?.vision);
  const parts: string[] = [];
  if (visionDown) {
    const why = cause(health?.vision?.last_error);
    parts.push(`CAPTCHA vision (${visionName}) unavailable${why ? `: ${why}` : ""}.`);
  }
  if (textDown) {
    const why = cause(health?.text?.last_error);
    parts.push(`Text features (${textName}) unavailable${why ? `: ${why}` : ""}.`);
    parts.push(`Handshake uses keyword rules. ${KEYWORD_ACT_COPY}`);
  } else {
    parts.push(`Text features on ${textName} are working.`);
  }
  if (textDown && !visionDown) {
    parts.push(`CAPTCHA vision (${visionName}) is working.`);
  }
  return parts.join(" ");
}
