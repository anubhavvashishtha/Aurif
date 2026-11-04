import { createFileRoute } from "@tanstack/react-router";
import { HumanGate } from "@/components/aurif/human-gate";
import { aurifHead } from "@/lib/aurif-meta";

type GateSearch = { embed: boolean };

export const Route = createFileRoute("/gate")({
  validateSearch: (search: Record<string, unknown>): GateSearch => ({
    embed: search.embed === "1" || search.embed === 1 || search.embed === true,
  }),
  head: () => aurifHead("Human gate", "Aurif checks that a person is at the browser before the site opens."),
  component: GatePage,
});

function GatePage() {
  const { embed } = Route.useSearch();
  return <HumanGate embed={embed} />;
}
