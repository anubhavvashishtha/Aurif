export function aurifHead(title: string, description: string) {
  return { meta: [
    { title: `${title} — Aurif` },
    { name: "description", content: description },
    { property: "og:title", content: `${title} — Aurif` },
    { property: "og:description", content: description },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] };
}