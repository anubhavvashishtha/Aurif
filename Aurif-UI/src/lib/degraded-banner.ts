/** Copy for the no-key / degraded banner. Matches keyword-rule handshake scoring. */
export const KEYWORD_ACT_COPY =
  "Act is granted only for a clear shopping request. Export, scraping, or collecting every price stays view-only.";

export function degradedModelWarning(detail: string): string {
  const rules = `Handshake uses keyword rules. ${KEYWORD_ACT_COPY} The human gate can fall back without vision.`;
  if (detail.trim()) return `Model degraded (${detail}). ${rules}`;
  return `Model key missing or the last call failed. ${rules}`;
}
